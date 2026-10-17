import importlib.machinery
import importlib.util
import contextlib
import io
import json
import os
import signal
import subprocess
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

    def test_project_context_files_walk_to_git_root_and_estimate_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory)
            repo = outside / "repo"
            nested = repo / "src" / "package"
            nested.mkdir(parents=True)
            (repo / ".git").mkdir()
            (outside / "CLAUDE.md").write_bytes(b"outside")
            (repo / "QWEN.md").write_bytes(b"1234")
            (repo / "src" / "AGENTS.md").write_bytes(b"12345")
            (nested / "CLAUDE.md").write_bytes(b"123456789")

            self.assertEqual(
                alia.project_context_files(nested),
                [
                    (nested / "CLAUDE.md", 3),
                    (repo / "src" / "AGENTS.md", 2),
                    (repo / "QWEN.md", 1),
                ],
            )

    def test_context_budget_warning_above_quarter_of_auto_compaction(self):
        profile = {"ctx": 65536}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            context = root / "CLAUDE.md"
            context.write_bytes(b"x" * 32536)  # 8,134 tokens: exactly below the warning.
            self.assertIsNone(alia.context_budget_warning(profile, root))
            context.write_bytes(b"x" * 32540)
            warning = alia.context_budget_warning(profile, root)
            self.assertIn(str(context), warning)
            self.assertIn("8135", warning)
            self.assertIn("resent with every request", warning)
        self.assertEqual(alia.project_context_summary([]), "none")

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


class EnvironmentContextTests(unittest.TestCase):
    def test_create_environment_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path = alia.write_environment_context(Path(directory))
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("# Alia environment\n\n"))
            self.assertIn(alia.ENVIRONMENT_START, text)
            self.assertIn(alia.ENVIRONMENT_END, text)
            self.assertIn("Foreground shell commands time out after 120 s", text)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_replace_preserves_user_text_before_and_after_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            qwen_home = Path(directory)
            path = qwen_home / "QWEN.md"
            before = b"# User context\r\nkeep before\n"
            after = b"\r\nkeep after\r\n"
            path.write_bytes(
                before + alia.ENVIRONMENT_START.encode() + b"\n- stale\n" +
                alia.ENVIRONMENT_END.encode() + after
            )
            alia.write_environment_context(qwen_home)
            updated = path.read_bytes()
            self.assertTrue(updated.startswith(before + alia.ENVIRONMENT_START.encode()))
            self.assertTrue(updated.endswith(alia.ENVIRONMENT_END.encode() + after))
            self.assertNotIn(b"stale", updated)

    def test_append_preserves_existing_user_content(self):
        with tempfile.TemporaryDirectory() as directory:
            qwen_home = Path(directory)
            path = qwen_home / "QWEN.md"
            original = b"# My notes\r\nDo not change this."
            path.write_bytes(original)
            alia.write_environment_context(qwen_home)
            updated = path.read_bytes()
            self.assertTrue(updated.startswith(original + b"\n\n"))
            self.assertIn(alia.ENVIRONMENT_START.encode(), updated)

    def test_python_and_pip_notes_when_only_python3_exists(self):
        commands = {"python": None, "python3": "/usr/bin/python3", "pip": None}
        with mock.patch.object(alia.shutil, "which", side_effect=commands.get):
            notes = alia.environment_notes()
        self.assertIn("Use `python3`; there is no `python` command.", notes)
        self.assertIn("Use `python3 -m pip`, not `pip`.", notes)

    def test_python_notes_are_omitted_when_python3_is_missing(self):
        with mock.patch.object(alia.shutil, "which", return_value=None):
            notes = alia.environment_notes()
        self.assertNotIn("Use `python3`; there is no `python` command.", notes)
        self.assertNotIn("Use `python3 -m pip`, not `pip`.", notes)


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
            self.assertNotIn("mcpServers", settings)
            self.assertEqual(settings["security"]["auth"]["selectedType"], "openai")
            self.assertEqual(settings["tools"]["approvalMode"], "default")
            self.assertEqual(settings["tools"]["truncateToolOutputThreshold"], 12000)
            self.assertEqual(settings["tools"]["truncateToolOutputLines"], 400)
            self.assertEqual(settings["tools"]["toolOutputBatchBudget"], 40000)
            self.assertEqual(settings["agents"]["maxParallelAgents"], 1)
            self.assertEqual(settings["skills"]["disabledLevels"], ["user"])
            self.assertEqual(
                settings["context"]["fileName"],
                ["QWEN.md", "AGENTS.md", "CLAUDE.md"],
            )
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
            self.assertTrue((target / "QWEN.md").exists())
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

    def test_python_shim_only_without_python(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "qwen-home"
            python3 = Path(directory) / "python3"
            python3.write_text("")
            which = {"python3": str(python3), "python": None}
            with mock.patch.object(alia.shutil, "which", side_effect=lambda name: which.get(name)):
                shim = alia.write_python_shim(home)
                self.assertEqual(os.readlink(shim), str(python3))
                self.assertEqual(alia.write_python_shim(home), shim)  # idempotent
                env = alia.qwen_environment({"qwen_home": home})
            self.assertTrue(env["PATH"].startswith(str(home / "bin")))
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "qwen-home"
            with mock.patch.object(alia.shutil, "which", return_value="/usr/bin/python"):
                self.assertIsNone(alia.write_python_shim(home))
            self.assertFalse((home / "bin").exists())

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

    def test_wait_for_health_scales_bar_and_records_load_time(self):
        class TtyBuffer(io.StringIO):
            def isatty(self):
                return True

        with tempfile.TemporaryDirectory() as directory:
            paths = self._paths(directory)
            paths["state"].mkdir(parents=True, exist_ok=True)
            load_file = paths["state"] / "last-load.json"
            load_file.write_text(json.dumps({"profile": "p", "seconds": 20}), encoding="utf-8")
            output = TtyBuffer()
            with mock.patch.object(alia, "health_ok", side_effect=[False, True]), \
                    mock.patch.object(alia, "process_start_ticks", return_value="1"), \
                    mock.patch.object(alia.time, "sleep"), redirect_stdout(output):
                alia.wait_for_health(4242, paths, timeout=30, profile_id="p")
            self.assertIn("~20", output.getvalue())
            self.assertEqual(json.loads(load_file.read_text(encoding="utf-8"))["profile"], "p")
            # A failed write of the load record must not abort a healthy start.
            with mock.patch.object(alia, "health_ok", return_value=True), \
                    mock.patch.object(alia, "write_private_text", side_effect=OSError("disk full")), \
                    redirect_stdout(io.StringIO()):
                alia.wait_for_health(4242, paths, timeout=30, profile_id="p")

    def test_main_status_dispatch(self):
        with mock.patch.object(alia, "cmd_status", return_value=3) as status, \
                redirect_stdout(io.StringIO()):
            self.assertEqual(alia.main(["status"]), 3)
        status.assert_called_once()
        with redirect_stderr(io.StringIO()):
            self.assertEqual(alia.main(["status", "extra"]), 1)
        alia.set_language("en")  # main() picks the host locale

    def test_doctor_shows_llama_build_and_ram_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = alia.user_paths(Path(directory))
            context = Path(directory) / "QWEN.md"
            context.write_bytes(b"12345")
            profiles = alia.load_profiles(ROOT / "profiles.json")
            hw = {"gpu_name": "NVIDIA GeForce RTX 3070", "vram_gb": 8.0, "ram_gb": 15.5,
                  "cpu_name": "CPU", "cpu_count": 16, "gpu_index": 0}
            with mock.patch.object(alia, "find_llama_server", return_value=(Path("/x/llama-server"), {"LD_LIBRARY_PATH": "/x"})), \
                    mock.patch.object(alia, "_version", return_value="version: test (build 1)") as version, \
                    mock.patch.object(alia, "mem_available_gb", return_value=1.0), \
                    mock.patch.object(alia, "ollama_loaded_models", return_value=None), \
                    mock.patch.object(alia, "port_open", return_value=False), \
                    mock.patch.object(alia, "health_ok", return_value=False), \
                    mock.patch.object(alia.Path, "cwd", return_value=Path(directory)), \
                    io.StringIO() as output, redirect_stdout(output):
                alia.cmd_doctor(profiles, hw, paths)
                text = output.getvalue()
            self.assertIn("version: test (build 1)", text)
            self.assertIn("⚠", text)
            self.assertIn(f"{context} (~2 tokens)", text)
            self.assertEqual(version.call_args_list[0].args[1]["LD_LIBRARY_PATH"], "/x")

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


class McpTests(unittest.TestCase):
    WHICH = {"npx": "/usr/bin/npx", "uvx": "/usr/bin/uvx"}

    def tearDown(self):
        alia.set_language("en")

    def _settings(self, directory, **kwargs):
        profile = alia.load_profiles(ROOT / "profiles.json")[0]
        output = alia.generate_settings(
            profile, {"gpu_name": "Test GPU"}, Path(directory) / "qwen-home", ROOT / "branding", **kwargs
        )
        return output.read_text(encoding="utf-8")

    def _main(self, directory, argv, which=None):
        which = self.WHICH if which is None else which
        with mock.patch.object(alia, "user_paths", return_value=alia.user_paths(Path(directory))), \
                mock.patch.object(alia.shutil, "which", side_effect=which.get), \
                mock.patch.dict(alia.os.environ, {"ALIA_LANG": "en"}), \
                io.StringIO() as output, io.StringIO() as error, \
                redirect_stdout(output), redirect_stderr(error):
            code = alia.main(argv)
            result = code, output.getvalue(), error.getvalue()
        alia.set_language("en")
        return result

    def test_no_mcp_config_emits_no_mcp_servers(self):
        for kwargs in ({}, {"mcp": None}, {"mcp": []}, {"mcp": ["unknown"]}, {"mcp": "browser"}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as directory:
                self.assertNotIn("mcpServers", json.loads(self._settings(directory, **kwargs)))

    def test_browser_and_search_are_emitted(self):
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(alia.Path, "home", return_value=Path(directory)):
            text = self._settings(directory, mcp=["search", "browser", "browser"])
        servers = json.loads(text)["mcpServers"]
        self.assertEqual(list(servers), ["browser", "search"])
        self.assertNotIn("<OUTDIR>", text)
        self.assertNotIn("requires", text)
        browser, search = servers["browser"], servers["search"]
        outdir = Path(directory) / ".cache" / "alia" / "playwright"
        self.assertTrue(outdir.is_absolute())
        self.assertIn(f"--output-dir={outdir}", browser["args"])
        self.assertEqual(browser["command"], "npx")
        self.assertIn("@playwright/mcp@0.0.83", browser["args"])
        self.assertEqual((browser["timeout"], search["timeout"]), (90000, 60000))
        self.assertIs(browser["trust"], False)
        self.assertIs(search["trust"], False)
        self.assertIs(browser["alwaysLoadTools"], True)
        self.assertIs(search["alwaysLoadTools"], True)
        self.assertEqual(len(browser["includeTools"]), 12)
        for unsafe in ("browser_evaluate", "browser_run_code_unsafe"):
            self.assertNotIn(unsafe, browser["includeTools"])
        self.assertEqual(search["command"], "uvx")
        self.assertEqual(search["args"], ["--from", "duckduckgo-mcp-server[browser]==0.7.0", "duckduckgo-mcp-server"])
        self.assertEqual(search["env"], {"DDG_SEARCH_RPM": "10", "DDG_FETCH_RPM": "10", "DDG_PARSE_MODE": "markdown"})
        self.assertNotIn("includeTools", search)
        # The catalog itself must stay untouched.
        self.assertIn("--output-dir=<OUTDIR>", alia.MCP_CATALOG["browser"]["args"])
        self.assertEqual(alia.MCP_CATALOG["browser"]["requires"], "npx")

    def test_mcp_config_preserves_other_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            alia.write_language_config(path, "de")
            alia.write_config(path, "chosen")
            alia.write_mcp_config(path, ["browser"])
            self.assertEqual(alia.read_config(path), {"lang": "de", "profile": "chosen", "mcp": ["browser"]})
            alia.write_mcp_config(path, [])
            self.assertEqual(alia.read_config(path), {"lang": "de", "profile": "chosen"})

    def test_prepare_runtime_passes_configured_mcp(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = alia.user_paths(Path(directory))
            alia.write_mcp_config(paths["config"], ["browser"])
            context = Path(directory) / "CLAUDE.md"
            context.write_bytes(b"x" * 40000)
            profiles = alia.load_profiles(ROOT / "profiles.json")
            hw = {"gpu_name": "NVIDIA GeForce RTX 3070", "vram_gb": 8.0, "ram_gb": 15.5}
            with mock.patch.object(alia, "ensure_model", return_value=Path("/m.gguf")), \
                    mock.patch.object(alia, "start_server", return_value=(4242, True, None)), \
                    mock.patch.object(alia, "generate_settings") as generate, \
                    mock.patch.object(alia.Path, "cwd", return_value=Path(directory)), \
                    mock.patch.dict(alia.os.environ, {}, clear=True), \
                    redirect_stdout(io.StringIO()) as output:
                self.assertIsNotNone(alia.prepare_runtime(profiles, hw, paths))
        self.assertEqual(generate.call_args.kwargs["mcp"], ["browser"])
        self.assertIn("Large project context", output.getvalue())

    def test_enable_disable_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = alia.user_paths(Path(directory))["config"]
            alia.write_config(path, "x")
            alia.write_language_config(path, "en")
            original = alia.read_config(path)
            code, output, _ = self._main(directory, ["mcp", "enable", "browser"])
            self.assertEqual(code, 0)
            self.assertIn("MCP server enabled: browser", output)
            self.assertNotIn("Warning", output)
            self.assertNotIn("duckduckgo", output)
            self.assertEqual(self._main(directory, ["mcp", "enable", "browser"])[0], 0)
            self.assertEqual(alia.read_config(path), {**original, "mcp": ["browser"]})
            self.assertEqual(self._main(directory, ["mcp", "enable", "search"])[0], 0)
            self.assertEqual(alia.read_config(path)["mcp"], ["browser", "search"])
            code, output, _ = self._main(directory, ["mcp", "disable", "search"])
            self.assertEqual(code, 0)
            self.assertIn("MCP server disabled: search", output)
            self.assertEqual(self._main(directory, ["mcp", "disable", "browser"])[0], 0)
            self.assertEqual(alia.read_config(path), original)

    def test_disable_inactive_server_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = alia.user_paths(Path(directory))["config"]
            code, output, _ = self._main(directory, ["mcp", "disable", "browser"])
            self.assertEqual(code, 0)
            self.assertIn("MCP server disabled: browser", output)
            self.assertFalse(path.exists())
            alia.write_mcp_config(path, ["search"])
            before = path.read_text(encoding="utf-8")
            self.assertEqual(self._main(directory, ["mcp", "disable", "browser"])[0], 0)
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_unknown_name_exits_1(self):
        with tempfile.TemporaryDirectory() as directory:
            for action in ("enable", "disable"):
                code, _, error = self._main(directory, ["mcp", action, "nope"])
                self.assertEqual(code, 1)
                self.assertIn("Unknown MCP server: nope (available: browser, search)", error)
            self.assertFalse(alia.user_paths(Path(directory))["config"].exists())

    def test_usage_errors_exit_1(self):
        with tempfile.TemporaryDirectory() as directory:
            for argv in (["mcp", "enable"], ["mcp", "foo"], ["mcp", "list", "x"], ["mcp", "enable", "a", "b"]):
                code, _, error = self._main(directory, argv)
                self.assertEqual(code, 1, argv)
                self.assertIn("Usage: alia mcp", error)

    def test_missing_requirement_warns_but_enables(self):
        with tempfile.TemporaryDirectory() as directory:
            code, output, _ = self._main(directory, ["mcp", "enable", "browser"], which={})
            self.assertEqual(code, 0)
            self.assertIn("Warning: 'npx' was not found", output)
            self.assertEqual(alia.read_config(alia.user_paths(Path(directory))["config"])["mcp"], ["browser"])

    def test_enable_search_prints_duckduckgo_note(self):
        with tempfile.TemporaryDirectory() as directory:
            code, output, _ = self._main(directory, ["mcp", "enable", "search"])
        self.assertEqual(code, 0)
        self.assertIn("duckduckgo", output.lower())
        self.assertIn("10 searches", output)

    def test_list_mentions_both_servers(self):
        with tempfile.TemporaryDirectory() as directory:
            for argv in (["mcp"], ["mcp", "list"]):
                code, output, _ = self._main(directory, argv, which={"npx": "/usr/bin/npx"})
                self.assertEqual(code, 0)
                self.assertIn("ENABLED", output)
                self.assertIn("npx found", output)
                self.assertIn("uvx missing", output)
                self.assertRegex(output, r"browser\s+no")
                self.assertRegex(output, r"search\s+no")
            self._main(directory, ["mcp", "enable", "search"])
            _, output, _ = self._main(directory, ["mcp", "list"])
            self.assertRegex(output, r"search\s+yes")
            self.assertRegex(output, r"browser\s+no")

    def test_list_in_german(self):
        with tempfile.TemporaryDirectory() as directory:
            code, output, _ = self._main(directory, ["--lang", "de", "mcp", "list"], which={"npx": "/usr/bin/npx"})
        self.assertEqual(code, 0)
        for text in ("AKTIV", "npx gefunden", "uvx fehlt", "nein", "DuckDuckGo"):
            self.assertIn(text, output)

    def test_usage_mentions_mcp_in_both_languages(self):
        for language in ("en", "de"):
            self.assertIn("alia mcp enable <name>", alia.tr_for(language, "usage.text"))
            self.assertIn("alia mcp test [name]", alia.tr_for(language, "usage.text"))

    def test_doctor_mcp_row(self):
        profiles = alia.load_profiles(ROOT / "profiles.json")
        hw = {"gpu_name": "NVIDIA GeForce RTX 3070", "vram_gb": 8.0, "ram_gb": 15.5,
              "cpu_name": "CPU", "cpu_count": 16, "gpu_index": 0}

        def doctor(paths, which, language="en"):
            alia.set_language(language)
            with mock.patch.object(alia, "find_llama_server", return_value=(Path("/x/llama-server"), {})), \
                    mock.patch.object(alia, "_version", return_value="version: test (build 1)"), \
                    mock.patch.object(alia, "mem_available_gb", return_value=None), \
                    mock.patch.object(alia, "ollama_loaded_models", return_value=None), \
                    mock.patch.object(alia, "port_open", return_value=False), \
                    mock.patch.object(alia, "health_ok", return_value=False), \
                    mock.patch.object(alia.shutil, "which", side_effect=which), \
                    io.StringIO() as output, redirect_stdout(output):
                code = alia.cmd_doctor(profiles, hw, paths)
                line = next(row for row in output.getvalue().splitlines() if "MCP" in row)
            return code, line

        def all_found(name):
            return f"/usr/bin/{name}"

        def no_uvx(name):
            return None if name == "uvx" else f"/usr/bin/{name}"

        with tempfile.TemporaryDirectory() as directory:
            paths = alia.user_paths(Path(directory))
            code_none, line = doctor(paths, all_found)
            self.assertRegex(line, r"MCP\S*\s+none$")
            self.assertRegex(doctor(paths, all_found, "de")[1], r"MCP\S*\s+keine$")
            alia.write_mcp_config(paths["config"], ["browser", "search"])
            code_ok, line = doctor(paths, all_found)
            self.assertTrue(line.endswith("browser, search · check: alia mcp test"))
            self.assertTrue(doctor(paths, all_found, "de")[1].endswith("browser, search · prüfen: alia mcp test"))
            code_warn, line = doctor(paths, no_uvx)
            self.assertTrue(line.endswith("browser, search ⚠ · check: alia mcp test"))
        self.assertEqual(code_none, code_ok)
        self.assertEqual(code_none, code_warn)


FAKE_MCP_SERVER = r"""
import json, os, sys, time
log = open(os.environ["FAKE_LOG"], "a", encoding="utf-8")
log.write(json.dumps({"argv": sys.argv[1:], "pid": os.getpid(), "env": os.environ.get("FAKE_ENV"),
                     "qwen_home": os.environ.get("QWEN_HOME")}) + "\n")
log.flush()
mode = os.environ["FAKE_MODE"]
if mode == "exit":
    sys.stderr.write("first line\n" + "x" * 300 + "\n   \n")
    sys.exit(3)
if mode == "orphan":
    import subprocess
    # A detached grandchild keeps stdout open after the server's process group is killed.
    grandchild = subprocess.Popen(["setsid", "sleep", "30"])
    log.write(json.dumps({"grandchild": grandchild.pid}) + "\n")
    log.flush()
    mode = "hang"
for line in sys.stdin:
    message = json.loads(line)
    log.write(line)
    log.flush()
    if mode == "hang" or "id" not in message:
        continue
    def reply(payload):
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message["id"], **payload}) + "\n")
        sys.stdout.flush()
    if mode == "error":
        reply({"error": {"code": -32601, "message": "boom"}})
    elif message["method"] == "initialize":
        sys.stdout.write("not json\n")
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/message"}) + "\n")
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": 99, "result": {}}) + "\n")
        reply({"result": {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "fake"}}})
    else:
        # A server-to-client request reusing our id must not count as the response.
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message["id"], "method": "roots/list"}) + "\n")
        reply({"result": {"tools": [{"name": "alpha"}, {"name": "beta"}, {"name": "hidden"}, "junk"]}})
"""


class McpTestCommandTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.script = self.root / "fake_mcp.py"
        self.script.write_text(FAKE_MCP_SERVER, encoding="utf-8")
        self.log = self.root / "fake.log"

    def tearDown(self):
        self.directory.cleanup()
        alia.set_language("en")

    def _entry(self, mode, include=None):
        entry = {
            "command": alia.sys.executable, "args": [str(self.script), "--output-dir=<OUTDIR>"],
            "env": {"FAKE_MODE": mode, "FAKE_LOG": str(self.log), "FAKE_ENV": "set"},
            "timeout": 1000, "trust": False, "alwaysLoadTools": True, "requires": "python3",
        }
        if include is not None:
            entry["includeTools"] = include
        return entry

    def _log(self):
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def _main(self, argv, catalog):
        with mock.patch.dict(alia.MCP_CATALOG, catalog), \
                mock.patch.object(alia, "user_paths", return_value=alia.user_paths(self.root)), \
                mock.patch.object(alia.Path, "home", return_value=self.root), \
                mock.patch.dict(alia.os.environ, {"ALIA_LANG": "en"}), \
                io.StringIO() as output, io.StringIO() as error, \
                redirect_stdout(output), redirect_stderr(error):
            code = alia.main(argv)
            result = code, output.getvalue(), error.getvalue()
        alia.set_language("en")
        return result

    def test_protocol_matches_generated_settings(self):
        with mock.patch.object(alia.Path, "home", return_value=self.root):
            entry = alia.mcp_servers(["browser"])["browser"] | {
                "command": alia.sys.executable,
                "args": [str(self.script), "--output-dir=" + str(self.root / ".cache/alia/playwright")],
                "env": self._entry("ok")["env"],
            }
        paths = alia.user_paths(self.root)
        with mock.patch.dict(alia.os.environ, {"QWEN_HOME": "/elsewhere"}):
            self.assertEqual(alia.mcp_probe(entry, alia.qwen_environment(paths), timeout=30), ["alpha", "beta", "hidden"])
        started, initialize, initialized, tools_list = self._log()
        self.assertEqual(started["env"], "set")
        self.assertEqual(started["qwen_home"], str(paths["qwen_home"]))
        self.assertEqual(initialize["method"], "initialize")
        self.assertEqual(initialize["params"]["protocolVersion"], "2025-06-18")
        self.assertEqual(initialize["params"]["clientInfo"]["name"], "alia")
        self.assertEqual(initialized, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual((tools_list["id"], tools_list["method"]), (2, "tools/list"))

    def test_enabled_servers_pass_and_filter_include_tools(self):
        catalog = {"browser": self._entry("ok", include=["alpha", "beta", "gamma"]), "search": self._entry("ok")}
        alia.write_mcp_config(alia.user_paths(self.root)["config"], ["browser", "search"])
        code, output, _ = self._main(["mcp", "test"], catalog)
        self.assertEqual(code, 0)
        self.assertRegex(output, r"browser: OK, 2 tools in [0-9.]+ s: alpha, beta\n")
        self.assertRegex(output, r"search: OK, 3 tools in [0-9.]+ s: alpha, beta, hidden\n")
        outdir = str(self.root / ".cache" / "alia" / "playwright")
        self.assertEqual([item["argv"] for item in self._log() if "argv" in item], [[f"--output-dir={outdir}"]] * 2)
        qwen_home = str(alia.user_paths(self.root)["qwen_home"])
        self.assertEqual([item["qwen_home"] for item in self._log() if "argv" in item], [qwen_home] * 2)

    def test_server_without_allowed_tools_fails(self):
        code, output, _ = self._main(["mcp", "test", "browser"], {"browser": self._entry("ok", include=["gamma"])})
        self.assertEqual(code, 1)
        self.assertIn("browser: failed: the server listed no allowed tools", output)
        code, output, _ = self._main(["--lang", "de", "mcp", "test", "browser"], {"browser": self._entry("ok", include=[])})
        self.assertEqual(code, 1)
        self.assertIn("der Server hat keine erlaubten Tools gemeldet", output)

    def test_named_server_and_failures_exit_1(self):
        catalog = {"browser": self._entry("ok"), "search": self._entry("error")}
        code, output, _ = self._main(["mcp", "test", "search"], catalog)
        self.assertEqual(code, 1)
        self.assertIn("search: failed: initialize returned an error:", output)
        self.assertIn("boom", output)
        self.assertNotIn("browser", output)
        code, output, _ = self._main(["mcp", "test", "browser"], {"browser": self._entry("exit")})
        self.assertEqual(code, 1)
        self.assertIn("browser: failed: the server exited before answering: " + "x" * 200 + "\n", output)
        self.assertNotIn("first line", output)
        missing = self._entry("ok") | {"command": "alia-missing-command"}
        code, output, _ = self._main(["mcp", "test", "browser"], {"browser": missing})
        self.assertEqual(code, 1)
        self.assertIn("browser: failed: command not found: alia-missing-command\n", output)
        self.assertNotIn("Errno", output)
        code, output, _ = self._main(["--lang", "de", "mcp", "test", "browser"], {"browser": missing})
        self.assertIn("Befehl nicht gefunden: alia-missing-command", output)

    def test_no_enabled_server(self):
        code, output, _ = self._main(["mcp", "test"], {})
        self.assertEqual(code, 0)
        self.assertIn("No MCP server is enabled", output)

    def test_unknown_name_and_usage_errors(self):
        code, _, error = self._main(["mcp", "test", "nope"], {})
        self.assertEqual(code, 1)
        self.assertIn("Unknown MCP server: nope (available: browser, search)", error)
        code, _, error = self._main(["mcp", "test", "browser", "search"], {})
        self.assertEqual(code, 1)
        self.assertIn("alia mcp test [name]", error)

    def test_timeout_terminates_child(self):
        started = alia.time.monotonic()
        with self.assertRaisesRegex(RuntimeError, r"no answer within 0.5 s"):
            alia.mcp_probe(self._entry("hang"), dict(os.environ), timeout=0.5)
        self.assertLess(alia.time.monotonic() - started, 10)
        pid = self._log()[0]["pid"]
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)


    def test_start_error_is_reported_and_stderr_file_closed(self):
        script = self.root / "not-executable"
        script.write_text("#!/bin/sh\n", encoding="utf-8")
        script.chmod(0o644)
        entry = self._entry("ok") | {"command": str(script)}
        opened = []
        real_temporary_file = alia.tempfile.TemporaryFile

        def tracking_temporary_file(*args, **kwargs):
            opened.append(real_temporary_file(*args, **kwargs))
            return opened[-1]

        with mock.patch.object(alia.tempfile, "TemporaryFile", side_effect=tracking_temporary_file), \
                self.assertRaisesRegex(RuntimeError, r"^cannot start .*not-executable: Permission denied$"):
            alia.mcp_probe(entry, dict(os.environ), timeout=5)
        with mock.patch.object(alia.tempfile, "TemporaryFile", side_effect=tracking_temporary_file), \
                self.assertRaisesRegex(RuntimeError, r"^command not found: alia-missing-command$"):
            alia.mcp_probe(entry | {"command": "alia-missing-command"}, dict(os.environ), timeout=5)
        self.assertEqual(len(opened), 2)
        self.assertTrue(all(handle.closed for handle in opened))
        code, output, _ = self._main(["--lang", "de", "mcp", "test", "browser"], {"browser": entry})
        self.assertEqual(code, 1)
        self.assertIn("lässt sich nicht starten: Permission denied", output)

    def test_detached_grandchild_holding_stdout_does_not_block_timeout(self):
        started = alia.time.monotonic()
        try:
            with self.assertRaisesRegex(RuntimeError, r"no answer within 2 s"):
                alia.mcp_probe(self._entry("orphan"), dict(os.environ), timeout=2)
            elapsed = alia.time.monotonic() - started
        finally:
            for item in self._log():
                if "grandchild" in item:
                    with contextlib.suppress(ProcessLookupError):
                        os.kill(item["grandchild"], signal.SIGKILL)
        self.assertLess(elapsed, 5)
        self.assertTrue(any("grandchild" in item for item in self._log()))


class SandboxTests(unittest.TestCase):
    PROFILES = alia.load_profiles(ROOT / "profiles.json")
    HW = {"gpu_name": "NVIDIA GeForce RTX 3070", "vram_gb": 8.0, "ram_gb": 15.5,
          "cpu_name": "CPU", "cpu_count": 16, "gpu_index": 0}

    def setUp(self):
        # The real bwrap probe is covered in SandboxProbeTests; CI may have no bwrap.
        patcher = mock.patch.object(alia, "bwrap_problem", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        alia.set_language("en")

    @staticmethod
    def _which(*present):
        return lambda name: f"/usr/bin/{name}" if name in present else None

    def _git_repo(self, root):
        def git(*args):
            return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@localhost", *args],
                                  cwd=root, capture_output=True, text=True, check=True).stdout
        git("init", "-q")
        (root / "a.txt").write_text("one\n", encoding="utf-8")
        git("add", "a.txt")
        git("commit", "-qm", "start")
        return git

    def _snapshot(self, root):
        with io.StringIO() as output, redirect_stdout(output):
            alia.snapshot_pre_session(root)
            return output.getvalue()

    def test_settings_policy_only_with_sandbox(self):
        profile = self.PROFILES[0]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            plain = json.loads(alia.generate_settings(profile, {"gpu_name": None}, target, ROOT / "branding")
                               .read_text(encoding="utf-8"))
            self.assertNotIn("executionSandbox", plain["tools"])
            sandboxed = json.loads(alia.generate_settings(profile, {"gpu_name": None}, target, ROOT / "branding",
                                                          sandbox=True).read_text(encoding="utf-8"))
        policy = sandboxed["tools"]["executionSandbox"]
        self.assertEqual(policy, {"backend": "auto", "filesystem": "workspace-write", "network": "closed"})
        self.assertEqual(sandboxed["tools"]["approvalMode"], "default")
        policy["network"] = "open"
        self.assertEqual(alia.SANDBOX_POLICY["network"], "closed")

    def test_require_sandbox_needs_bwrap_and_no_mcp(self):
        with mock.patch.object(alia.shutil, "which", side_effect=self._which()):
            with self.assertRaisesRegex(RuntimeError, "bubblewrap"):
                alia.require_sandbox({})
        with mock.patch.object(alia.shutil, "which", side_effect=self._which("bwrap")):
            alia.require_sandbox({"mcp": ["unknown"]})
            with self.assertRaisesRegex(RuntimeError, r"does not support MCP servers \(enabled: browser, search\)"):
                alia.require_sandbox({"mcp": ["search", "browser"]})

    def test_prepare_runtime_checks_before_server_start(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = alia.user_paths(Path(directory))
            alia.write_mcp_config(paths["config"], ["browser"])
            for which, message in ((self._which(), "bwrap"), (self._which("bwrap"), "MCP")):
                with self.subTest(message=message), \
                        mock.patch.object(alia.shutil, "which", side_effect=which), \
                        mock.patch.object(alia, "ensure_model") as ensure, \
                        mock.patch.object(alia, "start_server") as start, \
                        redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(RuntimeError, message):
                        alia.prepare_runtime(self.PROFILES, self.HW, paths, sandbox=True)
                    ensure.assert_not_called()
                    start.assert_not_called()

    def test_prepare_runtime_snapshots_and_passes_sandbox(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = alia.user_paths(Path(directory))
            with mock.patch.object(alia.shutil, "which", side_effect=self._which("bwrap")), \
                    mock.patch.object(alia, "ensure_model", return_value=Path("/m.gguf")), \
                    mock.patch.object(alia, "start_server", return_value=(4242, True, None)), \
                    mock.patch.object(alia, "generate_settings") as generate, \
                    mock.patch.object(alia, "snapshot_pre_session") as snapshot, \
                    mock.patch.object(alia.Path, "cwd", return_value=Path(directory)), \
                    mock.patch.dict(alia.os.environ, {}, clear=True), \
                    redirect_stdout(io.StringIO()) as output:
                self.assertIsNotNone(alia.prepare_runtime(self.PROFILES, self.HW, paths, sandbox=True))
                self.assertIsNotNone(alia.prepare_runtime(self.PROFILES, self.HW, paths))
        snapshot.assert_called_once_with(Path(directory))
        self.assertEqual([call.kwargs["sandbox"] for call in generate.call_args_list], [True, False])
        self.assertEqual(output.getvalue().count("Sandbox: bwrap"), 1)

    def test_snapshot_non_repo_and_missing_git(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIn("Not a git repository", self._snapshot(Path(directory)))
            with mock.patch.object(alia.shutil, "which", return_value=None):
                self.assertIn("Not a git repository", self._snapshot(Path(directory)))

    def test_snapshot_clean_repo_writes_no_ref(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git = self._git_repo(root)
            output = self._snapshot(root)
            self.assertIn("no pre-session snapshot needed", output)
            self.assertNotIn("untracked", output)
            self.assertEqual(git("for-each-ref", "refs/alia"), "")

    def test_snapshot_dirty_repo_keeps_tree_and_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git = self._git_repo(root)
            (root / "a.txt").write_text("two\n", encoding="utf-8")
            (root / "b.txt").write_text("staged\n", encoding="utf-8")
            git("add", "b.txt")
            (root / "new.txt").write_text("untracked\n", encoding="utf-8")
            before = (git("status", "--porcelain"), git("diff"), git("diff", "--cached"), git("stash", "list"))
            index = root / ".git" / "index"
            index_before = (index.read_bytes(), index.stat().st_mtime_ns)
            scratch = sorted(Path(tempfile.gettempdir()).glob("alia-index-*"))
            output = self._snapshot(root)
            self.assertEqual((index.read_bytes(), index.stat().st_mtime_ns), index_before)
            self.assertEqual(sorted(Path(tempfile.gettempdir()).glob("alia-index-*")), scratch)
            self.assertIn("alia pre-session snapshot", git("reflog", "show", "refs/alia/pre-session"))
            after = (git("status", "--porcelain"), git("diff"), git("diff", "--cached"), git("stash", "list"))
            self.assertEqual(before, after)
            self.assertEqual(after[3], "")
            self.assertEqual((root / "a.txt").read_text(encoding="utf-8"), "two\n")
            commit = git("rev-parse", "refs/alia/pre-session").strip()
            self.assertIn(f"refs/alia/pre-session → {commit[:12]}", output)
            self.assertIn("git stash apply --index refs/alia/pre-session", output)
            self.assertIn("untracked files are not part", output)
            self.assertEqual(git("show", f"{commit}:a.txt"), "two\n")
            self.assertEqual(git("show", f"{commit}:b.txt"), "staged\n")
            refs = git("for-each-ref", "--format=%(refname)").split()
            self.assertEqual([ref for ref in refs if not ref.startswith("refs/heads/")], ["refs/alia/pre-session"])

    def test_snapshot_untracked_only_warns_without_ref(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git = self._git_repo(root)
            (root / "new.txt").write_text("untracked\n", encoding="utf-8")
            output = self._snapshot(root)
            self.assertIn("Warning: untracked files", output)
            self.assertIn("no pre-session snapshot needed", output)
            self.assertEqual(git("for-each-ref", "refs/alia"), "")

    def test_snapshot_ignores_index_lock_and_missing_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git = self._git_repo(root)
            (root / "a.txt").write_text("two\n", encoding="utf-8")
            lock = root / ".git" / "index.lock"
            lock.write_bytes(b"")
            self.assertIn("Pre-session snapshot", self._snapshot(root))
            self.assertTrue(lock.exists())
            lock.unlink()
            (root / ".git" / "index").unlink()
            git("update-ref", "-d", "refs/alia/pre-session")
            self.assertIn("Pre-session snapshot", self._snapshot(root))
            self.assertFalse((root / ".git" / "index").exists())

    def test_snapshot_stash_failure_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git = self._git_repo(root)
            git("checkout", "-qb", "other")
            (root / "a.txt").write_text("other\n", encoding="utf-8")
            git("commit", "-qam", "other")
            git("checkout", "-q", "-")
            (root / "a.txt").write_text("main\n", encoding="utf-8")
            git("commit", "-qam", "main")
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@localhost", "merge", "other"], cwd=root, capture_output=True, check=False)
            with io.StringIO() as output, redirect_stdout(output):
                with self.assertRaisesRegex(RuntimeError, r"git stash create \(Cannot save the current index state\)"):
                    alia.snapshot_pre_session(root)
                self.assertNotIn("no pre-session snapshot needed", output.getvalue())
            self.assertEqual(git("for-each-ref", "refs/alia"), "")
            with mock.patch.object(alia.subprocess, "run", return_value=mock.Mock(returncode=1, stdout="", stderr="")), \
                    mock.patch.object(alia, "git_run", return_value=mock.Mock(returncode=0, stdout=".git/index\n")):
                with self.assertRaisesRegex(RuntimeError, r"\(exit 1\)"):
                    self._snapshot(root)

    def test_snapshot_without_commit_and_old_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            self.assertIn("has no commit yet", self._snapshot(root))
            self.assertNotIn("Not a git repository", self._snapshot(root))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git = self._git_repo(root)
            self.assertNotIn("earlier session", self._snapshot(root))
            git("update-ref", "refs/alia/pre-session", "HEAD")
            output = self._snapshot(root)
            self.assertIn("no pre-session snapshot needed", output)
            self.assertIn("refs/alia/pre-session still holds a snapshot from an earlier session", output)
            self.assertEqual(git("rev-parse", "refs/alia/pre-session"), git("rev-parse", "HEAD"))

    def test_snapshot_ref_failure_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._git_repo(root)
            (root / "a.txt").write_text("two\n", encoding="utf-8")
            (root / ".git" / "refs" / "alia").write_text("not a directory\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Cannot store the pre-session snapshot"):
                self._snapshot(root)

    def test_flag_parsing(self):
        self.assertEqual(alia.extract_sandbox_flag(["--yolo", "--sandbox", "--", "-p"]), (True, ["--yolo", "--", "-p"]))
        self.assertEqual(alia.extract_sandbox_flag(["--", "--sandbox"]), (False, ["--", "--sandbox"]))
        self.assertEqual(alia.extract_sandbox_flag(["-c"]), (False, ["-c"]))
        with self.assertRaisesRegex(RuntimeError, "before '--'"):
            alia.parse_start_args(["--", "--sandbox"])
        with self.assertRaisesRegex(RuntimeError, "alia web does not support --sandbox"):
            alia.parse_web_args(["--no-open", "--sandbox"])

    def test_main_passes_flag_and_web_errors(self):
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(alia, "user_paths", return_value=alia.user_paths(Path(directory))), \
                mock.patch.object(alia, "detect_hardware", return_value=self.HW), \
                mock.patch.object(alia, "cmd_start", return_value=0) as start, \
                io.StringIO() as error, redirect_stderr(error):
            self.assertEqual(alia.main(["--lang", "en", "--sandbox", "--fast"]), 0)
            self.assertEqual(alia.main(["--lang", "en", "--fast"]), 0)
            self.assertEqual(alia.main(["--lang", "de", "web", "--sandbox"]), 1)
            self.assertIn("alia web unterstützt --sandbox nicht", error.getvalue())
        alia.set_language("en")
        self.assertEqual([call.kwargs["sandbox"] for call in start.call_args_list], [True, False])
        self.assertTrue(start.call_args_list[0].kwargs["fast"])

    def test_cmd_start_passes_sandbox(self):
        with mock.patch.object(alia, "prepare_runtime", return_value=None) as prepare:
            self.assertEqual(alia.cmd_start([], self.PROFILES, self.HW, {}, sandbox=True), 1)
        self.assertIs(prepare.call_args.args[-1], True)

    def test_usage_and_doctor_row(self):
        for language in ("en", "de"):
            self.assertIn("--sandbox", alia.tr_for(language, "usage.text"))
        for which, expected in ((self._which("bwrap", "npx", "uvx"), r"Sandbox\S*\s+bwrap$"),
                                (self._which("npx", "uvx"), r"Sandbox\S*\s+none \(install bubblewrap")):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory, \
                    mock.patch.object(alia, "find_llama_server", return_value=(None, {})), \
                    mock.patch.object(alia, "_version", return_value="test"), \
                    mock.patch.object(alia, "mem_available_gb", return_value=None), \
                    mock.patch.object(alia, "ollama_loaded_models", return_value=None), \
                    mock.patch.object(alia, "port_open", return_value=False), \
                    mock.patch.object(alia, "health_ok", return_value=False), \
                    mock.patch.object(alia.shutil, "which", side_effect=which), \
                    io.StringIO() as output, redirect_stdout(output):
                alia.cmd_doctor(self.PROFILES, self.HW, alia.user_paths(Path(directory)))
                line = next(row for row in output.getvalue().splitlines() if "Sandbox" in row)
            self.assertRegex(line, expected)



class SandboxProbeTests(unittest.TestCase):
    def tearDown(self):
        alia.set_language("en")

    def test_probe_results(self):
        with mock.patch.object(alia.subprocess, "run", return_value=mock.Mock(returncode=0, stderr="")) as run:
            self.assertIsNone(alia.bwrap_problem())
        self.assertEqual(run.call_args.args[0], ["bwrap", "--unshare-all", "--die-with-parent", "--ro-bind", "/", "/", "true"])
        self.assertEqual(run.call_args.kwargs["timeout"], 5)
        cases = (
            (mock.Mock(returncode=1, stderr="bwrap: No permissions to create new namespace\n"), "No permissions"),
            (mock.Mock(returncode=3, stderr=""), "exit 3"),
            (alia.subprocess.TimeoutExpired(["bwrap"], 5), "no answer within 5 s"),
            (PermissionError(13, "Permission denied"), "Permission denied"),
        )
        for outcome, expected in cases:
            kwargs = {"side_effect": outcome} if isinstance(outcome, BaseException) else {"return_value": outcome}
            with self.subTest(expected=expected), mock.patch.object(alia.subprocess, "run", **kwargs):
                self.assertIn(expected, alia.bwrap_problem())

    def test_unusable_bwrap_stops_start_and_shows_in_doctor(self):
        with mock.patch.object(alia.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), \
                mock.patch.object(alia, "bwrap_problem", return_value="no namespaces"):
            with self.assertRaisesRegex(RuntimeError, r"cannot create a sandbox \(no namespaces\)"):
                alia.require_sandbox({})
            with tempfile.TemporaryDirectory() as directory, \
                    mock.patch.object(alia, "find_llama_server", return_value=(None, {})), \
                    mock.patch.object(alia, "_version", return_value="test"), \
                    mock.patch.object(alia, "mem_available_gb", return_value=None), \
                    mock.patch.object(alia, "ollama_loaded_models", return_value=None), \
                    mock.patch.object(alia, "port_open", return_value=False), \
                    mock.patch.object(alia, "health_ok", return_value=False), \
                    io.StringIO() as output, redirect_stdout(output):
                alia.cmd_doctor(SandboxTests.PROFILES, SandboxTests.HW, alia.user_paths(Path(directory)))
                line = next(row for row in output.getvalue().splitlines() if "Sandbox" in row)
        self.assertTrue(line.endswith("bwrap not usable: no namespaces ⚠"))


if __name__ == "__main__":
    unittest.main()
