import importlib.machinery
import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("alia_module", str(ROOT / "alia"))
spec = importlib.util.spec_from_loader(loader.name, loader)
alia = importlib.util.module_from_spec(spec)
loader.exec_module(alia)
alia.set_language("en")


class ProfileMatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = alia.load_profiles(ROOT / "profiles.json")

    def test_8gb_machine_prefers_measured_35b(self):
        hw = {"gpu_name": "RTX 3070", "vram_gb": 8.0, "ram_gb": 15.5}
        profile, reason, warning = alia.choose_profile(self.profiles, hw)
        self.assertEqual(profile["id"], "rtx8gb-16gb-qwen36-35b")
        self.assertIn("measured", reason)
        self.assertFalse(warning)

    def test_24gb_machine_falls_back_to_unmeasured(self):
        hw = {"gpu_name": "RTX 4090", "vram_gb": 24.0, "ram_gb": 63.0}
        profile, _, warning = alia.choose_profile(self.profiles, hw)
        self.assertEqual(profile["id"], "rtx24gb-qwen36-35b-q4")
        self.assertTrue(warning)

    def test_no_nvidia_gpu_has_no_profile(self):
        profile, reason, warning = alia.choose_profile(
            self.profiles, {"gpu_name": None, "vram_gb": 0, "ram_gb": 64}
        )
        self.assertIsNone(profile)
        self.assertIn("CPU profile", reason)
        self.assertTrue(warning)

    def test_pin_overrides_matching(self):
        hw = {"gpu_name": "RTX", "vram_gb": 8, "ram_gb": 16}
        profile, reason, _ = alia.choose_profile(
            self.profiles, hw, "rtx8gb-qwen35-9b-fast"
        )
        self.assertEqual(profile["id"], "rtx8gb-qwen35-9b-fast")
        self.assertIn("pinned", reason)

    def test_cmd_profiles_renders_every_shipped_profile(self):
        hw = {"gpu_name": "RTX", "vram_gb": 8, "ram_gb": 16}
        for profile in self.profiles:
            with self.subTest(profile=profile["id"]), io.StringIO() as output, redirect_stdout(output):
                self.assertEqual(alia.cmd_profiles([profile], hw, profile["id"]), 0)
                self.assertIn(profile["id"], output.getvalue())

    def test_every_numeric_metric_names_its_source_run_and_context(self):
        for profile in self.profiles:
            measured = profile.get("measured")
            if not measured:
                continue
            sources = measured.get("metric_sources", {})
            for key, value in measured.items():
                if key.endswith("_tps") or "_tps_" in key or key == "mtp_acceptance":
                    with self.subTest(profile=profile["id"], metric=key):
                        self.assertIsInstance(value, (int, float))
                        self.assertIn("bench/results/", sources[key])
                        self.assertIn("ctx ", sources[key])


class ConfigTests(unittest.TestCase):
    def test_pin_and_unpin(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            alia.write_config(path, "chosen")
            self.assertEqual(alia.read_config(path), {"profile": "chosen"})
            alia.write_config(path, None)
            self.assertEqual(alia.read_config(path), {})

    def test_profile_changes_preserve_language(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            alia.write_language_config(path, "de")
            alia.write_config(path, "chosen")
            self.assertEqual(
                alia.read_config(path), {"lang": "de", "profile": "chosen"}
            )
            alia.write_config(path, None)
            self.assertEqual(alia.read_config(path), {"lang": "de"})

    def test_valid_json_that_is_not_an_object_is_a_localized_error(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = alia.user_paths(Path(directory))
            paths["config"].parent.mkdir(parents=True)
            paths["config"].write_text("[1, 2, 3]\n", encoding="utf-8")
            with mock.patch.object(alia, "user_paths", return_value=paths), mock.patch.dict(
                alia.os.environ, {"ALIA_LANG": "de"}, clear=True
            ), io.StringIO() as error, redirect_stderr(error):
                self.assertEqual(alia.main(["--version"]), 1)
                self.assertIn("Konfiguration muss ein JSON-Objekt sein", error.getvalue())
                self.assertNotIn("Traceback", error.getvalue())
        alia.set_language("en")


class LanguageTests(unittest.TestCase):
    def test_resolution_precedence(self):
        locale = {"LC_ALL": "de_DE.UTF-8", "LANG": "en_US.UTF-8"}
        self.assertEqual(
            alia.resolve_language("en", {**locale, "ALIA_LANG": "de"}, {"lang": "de"}),
            "en",
        )
        self.assertEqual(
            alia.resolve_language(None, {**locale, "ALIA_LANG": "en"}, {"lang": "de"}),
            "en",
        )
        self.assertEqual(
            alia.resolve_language(None, locale, {"lang": "en"}), "en"
        )
        self.assertEqual(alia.resolve_language(None, locale, {}), "de")

    def test_locale_order_auto_and_fallback(self):
        self.assertEqual(
            alia.resolve_language(
                "auto",
                {"LC_ALL": "", "LC_MESSAGES": "de_DE.UTF-8", "LANG": "en_US"},
                {"lang": "en"},
            ),
            "de",
        )
        self.assertEqual(
            alia.resolve_language(None, {"LANG": "fr_FR.UTF-8"}, {}), "en"
        )
        self.assertEqual(
            alia.resolve_language("xx", {"LANG": "de_DE.UTF-8"}, {"lang": "de"}),
            "en",
        )
        self.assertEqual(alia.resolve_language(None, {}, {}), "en")

    def test_flag_is_removed_before_dispatch(self):
        self.assertEqual(
            alia.extract_language_flag(["doctor", "--lang", "de"]),
            ("de", ["doctor"]),
        )
        self.assertEqual(
            alia.extract_language_flag(["--lang=en", "web", "--no-open"]),
            ("en", ["web", "--no-open"]),
        )

    def test_missing_key_falls_back_to_english(self):
        with tempfile.TemporaryDirectory() as directory:
            i18n = Path(directory)
            (i18n / "en.json").write_text(
                json.dumps({"only.english": "Hello {name}"}), encoding="utf-8"
            )
            (i18n / "de.json").write_text("{}", encoding="utf-8")
            alia.set_language("de", i18n)
            self.assertEqual(alia.tr("only.english", name="Alia"), "Hello Alia")
        alia.set_language("en")

    def test_german_contains_every_english_key(self):
        english = alia.load_messages("en")
        german = alia.load_messages("de")
        self.assertEqual(set(english) - set(german), set())

    def test_lang_command_accepts_locale_form(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            alia, "user_paths", return_value=alia.user_paths(Path(directory))
        ), io.StringIO() as output, redirect_stdout(output):
            self.assertEqual(alia.main(["lang", "de_DE.UTF-8"]), 0)
            config = alia.read_config(Path(directory) / ".config/alia/config.json")
            self.assertEqual(config["lang"], "de")
        alia.set_language("en")


class ArgumentTests(unittest.TestCase):
    def test_two_gpu_detection_constrains_server_to_largest_gpu(self):
        def command_output(args):
            if args[0] == "nvidia-smi":
                return "0, Small GPU, 8192\n1, Large GPU, 24576"
            return ""

        environment = {k: v for k, v in os.environ.items() if k != "CUDA_VISIBLE_DEVICES"}
        with mock.patch.object(alia, "_run_text", side_effect=command_output), \
                mock.patch.dict(os.environ, environment, clear=True):
            hw = alia.detect_hardware()
        self.assertEqual((hw["gpu_index"], hw["gpu_name"], hw["vram_gb"]), (1, "Large GPU", 24.0))

        profile = alia.load_profiles(ROOT / "profiles.json")[0]
        process = mock.Mock(pid=4242)
        process.poll.return_value = None
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                "state": root, "pid": root / "server.pid", "server_state": root / "server.json",
                "log": root / "server.log",
            }
            with mock.patch.object(
                alia, "find_llama_server", return_value=(Path("/bin/llama-server"), {})
            ), mock.patch.object(alia, "managed_pid", return_value=None), mock.patch.object(
                alia, "health_ok", return_value=False
            ), mock.patch.object(alia, "unload_ollama"), mock.patch.object(alia, "mem_available_gb", return_value=None), mock.patch.object(alia, "mem_available_gb", return_value=5.0), mock.patch.object(
                alia, "process_start_ticks", return_value="123"
            ), mock.patch.object(alia.subprocess, "Popen", return_value=process) as popen, \
                    mock.patch.dict(os.environ, environment, clear=True), redirect_stdout(io.StringIO()) as out:
                alia.start_server(profile, Path("/model.gguf"), paths, hw["gpu_index"])
            self.assertIn("5.0", out.getvalue())
            self.assertEqual(popen.call_args.kwargs["env"]["CUDA_VISIBLE_DEVICES"], "1")
            self.assertEqual(json.loads(paths["server_state"].read_text())["gpu_index"], 1)

    def test_inherited_cuda_mask_limits_detection_and_is_kept(self):
        def command_output(args):
            if args[0] == "nvidia-smi":
                return "0, Small GPU, 8192\n1, Large GPU, 24576"
            return ""

        with mock.patch.object(alia, "_run_text", side_effect=command_output), \
                mock.patch.dict(os.environ, {"CUDA_VISIBLE_DEVICES": "0"}):
            hw = alia.detect_hardware()
        self.assertEqual((hw["gpu_index"], hw["gpu_name"]), (0, "Small GPU"))

        profile = alia.load_profiles(ROOT / "profiles.json")[0]
        process = mock.Mock(pid=4242)
        process.poll.return_value = None
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                "state": root, "pid": root / "server.pid", "server_state": root / "server.json",
                "log": root / "server.log",
            }
            with mock.patch.object(
                alia, "find_llama_server", return_value=(Path("/bin/llama-server"), {})
            ), mock.patch.object(alia, "managed_pid", return_value=None), mock.patch.object(
                alia, "health_ok", return_value=False
            ), mock.patch.object(alia, "unload_ollama"), mock.patch.object(alia, "mem_available_gb", return_value=None), mock.patch.object(
                alia, "process_start_ticks", return_value="123"
            ), mock.patch.object(alia.subprocess, "Popen", return_value=process) as popen, \
                    mock.patch.dict(os.environ, {"CUDA_VISIBLE_DEVICES": "GPU-uuid-a"}):
                alia.start_server(profile, Path("/model.gguf"), paths, 1)
            self.assertEqual(popen.call_args.kwargs["env"]["CUDA_VISIBLE_DEVICES"], "GPU-uuid-a")

    def test_llama_library_path_is_prepended_for_configured_and_default_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configured = root / "custom" / "llama-server"
            preferred = root / "src/llama.cpp/build/bin/llama-server"
            for binary in (configured, preferred):
                binary.parent.mkdir(parents=True, exist_ok=True)
                binary.touch(mode=0o700)
            with mock.patch.dict(
                alia.os.environ,
                {"ALIA_LLAMA_SERVER": str(configured), "LD_LIBRARY_PATH": "/existing/lib"},
                clear=True,
            ):
                binary, env = alia.find_llama_server()
            self.assertEqual(binary, configured)
            self.assertEqual(env["LD_LIBRARY_PATH"], f"{configured.parent}:/existing/lib")
            with mock.patch.dict(alia.os.environ, {"LD_LIBRARY_PATH": "/existing/lib"}, clear=True), \
                    mock.patch.object(alia.Path, "home", return_value=root):
                binary, env = alia.find_llama_server()
            self.assertEqual(binary, preferred)
            self.assertEqual(env["LD_LIBRARY_PATH"], f"{preferred.parent}:/existing/lib")

    def test_qwen_version_match_is_exact(self):
        self.assertTrue(alia.qwen_version_supported("Qwen Code v0.25.1"))
        for output in ("0.25.10", "10.25.1", "0.25.1-beta"):
            with self.subTest(output=output):
                self.assertFalse(alia.qwen_version_supported(output))

    def test_qwen_compaction_thresholds_match_qwen_code(self):
        # Values from Qwen Code 0.25.1 computeThresholds(); 10408 is the hard limit the old 9B window hit.
        self.assertEqual(alia.qwen_compaction_thresholds(33408), (408, 10408))
        self.assertEqual(alia.qwen_compaction_thresholds(65536), (32536, 42536))
        self.assertEqual(alia.qwen_compaction_thresholds(32768), (27852, 30852))
        self.assertTrue(alia.compaction_too_early(33408))

    def test_compaction_texts(self):
        self.assertIn("408", alia.compaction_warning(33408))
        self.assertIn("10408", alia.compaction_warning(33408))
        self.assertIsNone(alia.compaction_warning(65536))
        self.assertTrue(alia.compaction_summary(33408).endswith("⚠"))
        self.assertIn("42536", alia.compaction_summary(65536))
        self.assertFalse(alia.compaction_summary(65536).endswith("⚠"))

    def test_ram_warning(self):
        profile = {"id": "large", "ram_free_gb": 11}
        self.assertIsNone(alia.ram_warning(profile, 12.0))
        self.assertIsNone(alia.ram_warning(profile, None))
        self.assertIsNone(alia.ram_warning({}, 2.0))
        warning = alia.ram_warning(profile, 9.4)
        self.assertIn("9.4", warning)
        self.assertIn("11", warning)
        self.assertIn("rtx8gb-qwen35-9b-fast", warning)
        light = {"id": "rtx8gb-qwen35-9b-fast", "ram_free_gb": 11}
        self.assertNotIn("alia use", alia.ram_warning(light, 9.4))

    def test_load_bar_scales_to_last_load_time(self):
        self.assertEqual(alia.load_bar(15, None), "█████░░░░░")
        self.assertEqual(alia.load_bar(15, 60), "██░░░░░░░░")
        self.assertEqual(alia.load_bar(90, 60), "██████████")

    def test_mem_available_reads_meminfo(self):
        meminfo = "MemTotal:       16000000 kB\nMemAvailable:    9961472 kB\n"
        with mock.patch.object(alia.Path, "read_text", return_value=meminfo):
            self.assertAlmostEqual(alia.mem_available_gb(), 9.5, places=2)
        with mock.patch.object(alia.Path, "read_text", side_effect=OSError):
            self.assertIsNone(alia.mem_available_gb())

    def test_offloading_default_profile_states_its_ram_need(self):
        profile = next(p for p in alia.load_profiles(ROOT / "profiles.json") if p["id"] == "rtx8gb-16gb-qwen36-35b")
        self.assertGreater(profile["ram_free_gb"], 0)
        self.assertIn("bench/results/", profile["ram_free_source"])

    def test_bundled_profiles_leave_room_before_compaction(self):
        for profile in alia.load_profiles(ROOT / "profiles.json"):
            with self.subTest(profile=profile["id"]):
                self.assertFalse(alia.compaction_too_early(profile["ctx"]))

    def test_server_arguments(self):
        profile = alia.load_profiles(ROOT / "profiles.json")[0]
        args = alia.build_server_args(Path("/bin/llama-server"), profile, Path("/m.gguf"))
        self.assertEqual(args[:3], ["/bin/llama-server", "-m", "/m.gguf"])
        self.assertIn("--alias", args)
        self.assertIn(profile["id"], args)
        self.assertNotIn("--cache-ram", args)
        self.assertNotIn("-ngl", args)
        self.assertIn("--no-webui", args)
        self.assertEqual(args[args.index("--api-key") + 1], "local")
        self.assertEqual(args[args.index("--host") + 1], "127.0.0.1")
        self.assertEqual(args[args.index("--port") + 1], "8090")
        self.assertEqual(args[args.index("-c") + 1], str(profile["ctx"]))

    def test_profile_cannot_override_loopback_or_port(self):
        original = alia.load_profiles(ROOT / "profiles.json")[0]
        for server_args in (["--host", "0.0.0.0"], ["--host=0.0.0.0"], ["--port=9000"]):
            profile = dict(original)
            profile["server_args"] = server_args
            with self.subTest(server_args=server_args), self.assertRaisesRegex(
                RuntimeError, "must not override"
            ):
                alia.build_server_args(Path("/bin/llama-server"), profile, Path("/m.gguf"))

    def test_server_reuse_requires_matching_context(self):
        profile = alia.load_profiles(ROOT / "profiles.json")[0]
        state = {"profile": profile["id"], "ctx": profile["ctx"]}
        self.assertTrue(alia.server_state_matches_profile(state, profile))
        state["ctx"] = profile["ctx"] * 2
        self.assertFalse(alia.server_state_matches_profile(state, profile))

    def test_server_reuse_requires_exact_argv_model_and_binary(self):
        profile = alia.load_profiles(ROOT / "profiles.json")[0]
        model = Path("/models/model.gguf")
        binary = Path("/bin/llama-server")
        state = {
            "profile": profile["id"], "ctx": profile["ctx"],
            "model_path": str(model), "binary": str(binary), "port": alia.PORT,
            "argv": alia.build_server_args(binary, profile, model),
        }
        self.assertTrue(alia.server_state_matches_profile(state, profile, model, binary))
        for key, value in (("model_path", "/other.gguf"), ("binary", "/other/server")):
            changed = dict(state)
            changed[key] = value
            self.assertFalse(alia.server_state_matches_profile(changed, profile, model, binary))
        changed = dict(state)
        changed["argv"] = [*state["argv"], "--changed"]
        self.assertFalse(alia.server_state_matches_profile(changed, profile, model, binary))

    def test_alia_approval_arguments(self):
        self.assertEqual(alia.parse_start_args([]), ("default", [], False, 0.0))
        self.assertEqual(
            alia.parse_start_args(["--auto-edit", "--", "-p", "task"]),
            ("auto-edit", ["-p", "task"], False, 0.0),
        )
        self.assertEqual(
            alia.parse_start_args(["--yolo", "--fast", "--wait-gpu", "2.5"]),
            ("yolo", [], True, 2.5),
        )

    def test_session_arguments_precede_passthrough_arguments(self):
        cases = (
            (["-c"], ("default", ["--continue"], False, 0.0)),
            (["--resume"], ("default", ["--resume"], False, 0.0)),
            (["-r", "abc"], ("default", ["--resume", "abc"], False, 0.0)),
            (["-r", "--", "--foo"], ("default", ["--resume", "--foo"], False, 0.0)),
            (["--yolo", "-r", "abc", "--", "task"],
             ("yolo", ["--resume", "abc", "task"], False, 0.0)),
        )
        for arguments, expected in cases:
            with self.subTest(arguments=arguments):
                self.assertEqual(alia.parse_start_args(arguments), expected)

    def test_version_reads_llama_server_stderr(self):
        result = mock.Mock(stdout="", stderr="version: 0.6.0-dev (build 1, commit a0e6dc7)\n")
        with mock.patch.object(alia.subprocess, "run", return_value=result):
            self.assertEqual(
                alia._version(["llama-server", "--version"]),
                "version: 0.6.0-dev (build 1, commit a0e6dc7)",
            )

    def test_yolo_warning_is_red_on_a_terminal(self):
        class TerminalBuffer(io.StringIO):
            def isatty(self):
                return True

        stderr = TerminalBuffer()
        with mock.patch.dict(alia.os.environ, {}, clear=True), mock.patch.object(
            alia.sys, "stderr", stderr
        ):
            alia.warn_approval_mode("yolo")
        self.assertIn("\033[1;31mWARNING: YOLO mode active", stderr.getvalue())

    def test_qwen_arguments_are_unchanged(self):
        self.assertEqual(
            alia.build_qwen_command(["-p", "hello world"], qwen="/bin/qwen"),
            ["/bin/qwen", "-p", "hello world"],
        )

    def test_web_port_cannot_reuse_model_server_port(self):
        with self.assertRaises(RuntimeError):
            alia.parse_web_args(["--port", str(alia.PORT)])

    def test_web_arguments_default_to_loopback_and_open(self):
        self.assertEqual(
            alia.parse_web_args([]), (4170, True, None, "default", False, 0.0)
        )
        self.assertEqual(
            alia.build_web_command(qwen="/bin/qwen"),
            [
                "/bin/qwen", "serve", "--hostname", "127.0.0.1",
                "--port", "4170", "--open",
            ],
        )

    def test_web_arguments_accept_port_workspace_and_no_open(self):
        port, open_browser, workspace, approval_mode, fast, wait_gpu = alia.parse_web_args(
            [
                "--port", "4317", "--no-open", "--workspace", str(ROOT),
                "--auto-edit", "--fast", "--wait-gpu", "3",
            ]
        )
        self.assertEqual(port, 4317)
        self.assertFalse(open_browser)
        self.assertEqual(workspace, ROOT)
        self.assertEqual(approval_mode, "auto-edit")
        self.assertTrue(fast)
        self.assertEqual(wait_gpu, 3.0)
        self.assertEqual(
            alia.build_web_command(port, open_browser, workspace, qwen="qwen"),
            [
                "qwen", "serve", "--hostname", "127.0.0.1",
                "--port", "4317", "--workspace", str(ROOT),
            ],
        )


class LogoValidationTests(unittest.TestCase):
    def test_banner_logo_uses_display_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valid.txt"
            valid.write_text("界" * 100 + "\n", encoding="utf-8")
            self.assertEqual(alia.validate_banner_logo(valid), (True, "ok"))
            invalid = Path(directory) / "invalid.txt"
            invalid.write_text("界" * 101 + "\n", encoding="utf-8")
            accepted, reason = alia.validate_banner_logo(invalid)
            self.assertFalse(accepted)
            self.assertIn("202 columns", reason)

    def test_web_logo_is_valid(self):
        self.assertEqual(
            alia.validate_svg_logo(ROOT / "branding" / "logo-mark.svg"),
            (True, "ok"),
        )


class SettingsTests(unittest.TestCase):
    def test_qwen_environment_forces_resolved_ui_language(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = {"qwen_home": Path(directory)}
            with mock.patch.dict(alia.os.environ, {"QWEN_CODE_LANG": "zh"}, clear=True):
                alia.set_language("de")
                environment = alia.qwen_environment(paths)
            self.assertEqual(environment["QWEN_CODE_LANG"], "de")
            self.assertEqual(environment["QWEN_DISABLE_AUTO_TITLE"], "1")
            self.assertEqual(environment["QWEN_CODE_EMIT_TOOL_USE_SUMMARIES"], "0")
            self.assertEqual(environment["QWEN_STREAM_MAX_LIFETIME_MS"], "1800000")
        alia.set_language("en")

    def test_generation_is_isolated_and_complete(self):
        profile = alia.load_profiles(ROOT / "profiles.json")[0]
        hw = {"gpu_name": "Test GPU"}
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "qwen-home"
            output = alia.generate_settings(profile, hw, target, ROOT / "branding")
            settings = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(settings["model"]["name"], profile["id"])
            self.assertEqual(settings["security"]["auth"]["selectedType"], "openai")
            self.assertEqual(settings["tools"]["approvalMode"], "default")
            self.assertEqual(settings["tools"]["truncateToolOutputThreshold"], 12000)
            self.assertEqual(settings["tools"]["truncateToolOutputLines"], 400)
            self.assertEqual(settings["tools"]["toolOutputBatchBudget"], 40000)
            self.assertEqual(settings["agents"]["maxParallelAgents"], 1)
            self.assertFalse(settings["general"]["enableAutoUpdate"])
            self.assertTrue(settings["model"]["skipLoopDetection"])
            self.assertFalse(settings["ui"]["enableFollowupSuggestions"])
            self.assertFalse(settings["ui"]["enableUserFeedback"])
            self.assertIn("cron_create", settings["permissions"]["deny"])
            for core in ("read_file", "edit", "write_file", "run_shell_command", "grep_search", "glob"):
                self.assertNotIn(core, settings["permissions"]["deny"])
            self.assertFalse(settings["memory"]["enableManagedAutoMemory"])
            self.assertEqual(
                settings["modelProviders"]["openai"][0]["baseUrl"],
                "http://127.0.0.1:8090/v1",
            )
            self.assertEqual(
                settings["modelProviders"]["openai"][0]["generationConfig"][
                    "contextWindowSize"
                ],
                profile["ctx"],
            )
            self.assertEqual(settings["ui"]["customBannerTitle"], f"Alia {alia.VERSION}")
            self.assertEqual(
                settings["ui"]["brand"],
                {"name": "Alia", "logoPath": "branding/logo-mark.svg"},
            )
            self.assertTrue((target / "logo-large.txt").exists())
            self.assertTrue((target / "branding" / "logo-mark.svg").exists())
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertFalse((ROOT / ".qwen").exists())

    def test_ollama_unload_retries_models_reloaded_by_clients(self):
        # A client reloads model-a until the second unload; the retry waits one second.
        ps_answers = [[{"name": "model-a"}]] * 6 + [[]]
        posts = []
        clock = [0.0]

        def urlopen(request, timeout):
            if isinstance(request, alia.urllib.request.Request):
                posts.append(json.loads(request.data))
                body = {}
            else:
                body = {"models": ps_answers.pop(0)}
            response = mock.MagicMock()
            response.__enter__.return_value = io.BytesIO(json.dumps(body).encode())
            return response

        def sleep(seconds):
            clock[0] += seconds

        with mock.patch.object(alia.urllib.request, "urlopen", side_effect=urlopen), \
                mock.patch.object(alia.time, "sleep", side_effect=sleep), \
                mock.patch.object(alia.time, "monotonic", side_effect=lambda: clock[0]):
            self.assertEqual(alia.unload_ollama(), 2)
        self.assertEqual(posts, [{"model": "model-a", "keep_alive": 0}] * 2)
        self.assertEqual(ps_answers, [])

    def test_doctor_ollama_texts(self):
        alia.set_language("en")
        cases = (
            (None, "not running"),
            ([], "running, no model loaded"),
            ([{"name": "a"}, {"model": "b"}], "loaded: a, b – Alia unloads it at start"),
        )
        for models, expected in cases:
            with self.subTest(models=models), mock.patch.object(
                alia, "ollama_loaded_models", return_value=models
            ):
                self.assertEqual(alia.doctor_ollama_status(), expected)

    def test_generated_language_settings_for_english_and_german(self):
        profile = alia.load_profiles(ROOT / "profiles.json")[0]
        with tempfile.TemporaryDirectory() as directory:
            for language, prefix, status in (
                ("en", "local ·", "measured"),
                ("de", "lokal ·", "gemessen"),
            ):
                target = Path(directory) / language
                output = alia.generate_settings(
                    profile, {"gpu_name": "Test GPU"}, target,
                    ROOT / "branding", language=language,
                )
                settings = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(
                    settings["general"],
                    {
                        "language": language, "outputLanguage": "auto",
                        "enableAutoUpdate": False,
                    },
                )
                subtitle = settings["ui"]["customBannerSubtitle"]
                self.assertTrue(subtitle.startswith(prefix))
                self.assertIn(status, subtitle)
                output_rule = (target / "output-language.md").read_text(encoding="utf-8")
                self.assertIn("llm-output-language: auto", output_rule)
                self.assertIn("same language as the user's input", output_rule)
                self.assertNotIn("German", output_rule)

    def test_approval_mode_is_written_for_web_and_tui(self):
        profile = alia.load_profiles(ROOT / "profiles.json")[0]
        with tempfile.TemporaryDirectory() as directory:
            output = alia.generate_settings(
                profile, {"gpu_name": "Test GPU"}, Path(directory),
                ROOT / "branding", approval_mode="auto-edit",
            )
            settings = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(settings["tools"]["approvalMode"], "auto-edit")

    def test_fast_mode_disables_chat_template_thinking_and_marks_banner(self):
        profile = alia.load_profiles(ROOT / "profiles.json")[0]
        with tempfile.TemporaryDirectory() as directory:
            output = alia.generate_settings(
                profile, {"gpu_name": "Test GPU"}, Path(directory),
                ROOT / "branding", language="de", fast=True,
            )
            settings = json.loads(output.read_text(encoding="utf-8"))
            generation = settings["modelProviders"]["openai"][0]["generationConfig"]
            self.assertEqual(
                generation["extra_body"],
                {"chat_template_kwargs": {"enable_thinking": False}},
            )
            self.assertIn("schnell", settings["ui"]["customBannerSubtitle"])

    def test_default_mode_leaves_thinking_unspecified(self):
        profile = alia.load_profiles(ROOT / "profiles.json")[0]
        with tempfile.TemporaryDirectory() as directory:
            output = alia.generate_settings(
                profile, {"gpu_name": "Test GPU"}, Path(directory),
                ROOT / "branding",
            )
            generation = json.loads(output.read_text(encoding="utf-8"))[
                "modelProviders"
            ]["openai"][0]["generationConfig"]
            self.assertNotIn("extra_body", generation)


class GpuLockTests(unittest.TestCase):
    def test_environment_lock_overrides_config(self):
        self.assertEqual(
            alia.resolve_gpu_lock(
                {"gpu_lock": "/config.lock"}, {"ALIA_GPU_LOCK": "/env.lock"}
            ),
            Path("/env.lock"),
        )

    def test_busy_lock_aborts_immediately_without_starting(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            alia.fcntl, "flock", side_effect=BlockingIOError
        ) as flock, mock.patch.object(alia.time, "sleep") as sleep, mock.patch(
            "builtins.print"
        ) as output:
            lock_path = Path(directory) / "gpu.lock"
            with self.assertRaisesRegex(RuntimeError, "stayed busy"):
                with alia.GpuStartLock(lock_path, wait_seconds=0):
                    self.fail("busy lock must not enter start sequence")
            flock.assert_called_once()
            sleep.assert_not_called()
            output.assert_called_once()


class PidTests(unittest.TestCase):
    def _paths(self, root):
        state = Path(root)
        return {
            "state": state,
            "pid": state / "server.pid",
            "server_state": state / "server.json",
            "log": state / "server.log",
        }

    def test_stale_pid_is_not_killed(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._paths(directory)
            paths["pid"].write_text("4242\n", encoding="ascii")
            paths["server_state"].write_text(
                json.dumps({"pid": 4242, "start_ticks": "old"}), encoding="utf-8"
            )
            with mock.patch.object(alia, "process_start_ticks", return_value="new"), mock.patch.object(
                alia.os, "kill"
            ) as kill:
                self.assertFalse(alia.stop_server(paths, quiet=True))
                kill.assert_not_called()
            self.assertFalse(paths["pid"].exists())

    def test_matching_pid_gets_sigterm(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._paths(directory)
            paths["pid"].write_text("4242\n", encoding="ascii")
            paths["server_state"].write_text(
                json.dumps({"pid": 4242, "start_ticks": "same"}), encoding="utf-8"
            )
            with mock.patch.object(alia, "process_start_ticks", return_value="same"), mock.patch.object(
                alia, "signal_managed_process", return_value=True
            ) as send, mock.patch.object(alia, "wait_until_gone", return_value=True):
                self.assertTrue(alia.stop_server(paths, quiet=True, wait_seconds=0))
                send.assert_called_once_with(4242, "same", alia.signal.SIGTERM)

    def test_pid_files_remain_when_sigkill_cannot_stop_process(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._paths(directory)
            paths["pid"].write_text("4242\n", encoding="ascii")
            paths["server_state"].write_text(
                json.dumps({"pid": 4242, "start_ticks": "same"}), encoding="utf-8"
            )
            with mock.patch.object(alia, "process_start_ticks", return_value="same"), mock.patch.object(
                alia, "signal_managed_process", return_value=True
            ) as send, mock.patch.object(alia, "wait_until_gone", return_value=False):
                self.assertFalse(alia.stop_server(paths, quiet=True, wait_seconds=0, kill_wait_seconds=0))
            self.assertEqual(
                [call.args[2] for call in send.call_args_list],
                [alia.signal.SIGTERM, alia.signal.SIGKILL],
            )
            self.assertTrue(paths["pid"].exists())
            self.assertTrue(paths["server_state"].exists())

    def test_wait_for_health_aborts_when_child_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._paths(directory)
            paths["pid"].write_text("4242\n", encoding="ascii")
            process = mock.Mock()
            process.poll.return_value = 7
            with mock.patch.object(alia, "health_ok", return_value=False):
                with self.assertRaisesRegex(RuntimeError, "exited"):
                    alia.wait_for_health(4242, paths, timeout=30, process=process)
            process.wait.assert_called_once()

    def test_status_stopped_and_healthy(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._paths(directory)
            with mock.patch.object(alia, "managed_pid", return_value=None), \
                    io.StringIO() as output, redirect_stdout(output):
                self.assertEqual(alia.cmd_status(paths), 3)
                self.assertIn("stopped", output.getvalue())

            paths["server_state"].write_text("{}", encoding="utf-8")
            state = {
                "profile": "test-profile", "port": 8090, "model": "model.gguf",
            }
            with mock.patch.object(alia, "managed_pid", return_value=4242), \
                    mock.patch.object(alia, "read_server_state", return_value=state), \
                    mock.patch.object(alia, "health_ok", return_value=True), \
                    mock.patch.object(alia, "process_owns_listen_port", return_value=True), \
                    io.StringIO() as output, redirect_stdout(output):
                self.assertEqual(alia.cmd_status(paths), 0)
                text = output.getvalue()
                self.assertIn("PID     4242", text)
                self.assertIn("test-profile", text)
                self.assertIn("ready", text)
                self.assertIn("model.gguf", text)
            with mock.patch.object(alia, "managed_pid", return_value=4242), \
                    mock.patch.object(alia, "read_server_state", return_value=state), \
                    mock.patch.object(alia, "health_ok", return_value=True), \
                    mock.patch.object(alia, "process_owns_listen_port", return_value=False), \
                    io.StringIO() as output, redirect_stdout(output):
                self.assertEqual(alia.cmd_status(paths), 1)

    def test_interrupt_before_state_files_stops_new_child(self):
        profile = alia.load_profiles(ROOT / "profiles.json")[0]
        process = mock.Mock(pid=4242)
        process.poll.return_value = None
        with tempfile.TemporaryDirectory() as directory:
            paths = self._paths(directory)
            with mock.patch.object(
                alia, "find_llama_server", return_value=(Path("/bin/llama-server"), {})
            ), mock.patch.object(alia, "managed_pid", return_value=None), mock.patch.object(
                alia, "health_ok", return_value=False
            ), mock.patch.object(alia, "unload_ollama"), mock.patch.object(alia, "mem_available_gb", return_value=None), mock.patch.object(
                alia, "process_start_ticks", side_effect=KeyboardInterrupt
            ), mock.patch.object(alia.subprocess, "Popen", return_value=process):
                with self.assertRaises(KeyboardInterrupt):
                    alia.start_server(profile, Path("/model.gguf"), paths, 1)
            process.terminate.assert_called_once()
            process.wait.assert_called_once_with(timeout=2)
            self.assertFalse(paths["pid"].exists())
            self.assertFalse(paths["server_state"].exists())

    def test_keyboard_interrupt_during_startup_stops_child(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._paths(directory)
            process = mock.Mock()
            process.poll.return_value = None
            with mock.patch.object(alia, "health_ok", return_value=False), mock.patch.object(
                alia, "process_start_ticks", return_value="same"
            ), mock.patch.object(alia.time, "sleep", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    alia.wait_for_health(4242, paths, timeout=30, process=process)
            process.terminate.assert_called_once()
            process.wait.assert_called_once_with(timeout=2)


class FirstRunTests(unittest.TestCase):
    def test_incomplete_model_is_ignored(self):
        profile = alia.load_profiles(ROOT / "profiles.json")[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / profile["model"]["file"]
            candidate.write_bytes(b"partial")
            modified = json.loads(json.dumps(profile))
            modified["model"]["local_candidates"] = [str(candidate)]
            paths = {"models": root / "downloads"}
            self.assertIsNone(alia.find_model(modified, paths))

    def test_private_writes_use_private_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config" / "config.json"
            alia.write_config(path, "test")
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
