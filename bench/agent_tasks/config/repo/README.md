# appcfg

`load_config(path=None, env=None)` returns a dict. Precedence, lowest to highest:

1. `DEFAULTS` in `appcfg/defaults.py`
2. the JSON file at `path` (if given and it exists)
3. environment variables named `APP_<KEY>` (upper case), e.g. `APP_PORT=9000`

Values from the environment are converted to the type of the default value:
`int` for ints, `bool` for bools (`"1"`, `"true"`, `"yes"`, `"on"` are true, case-insensitive, everything else false),
and strings stay strings. Unknown `APP_*` variables are ignored. `env` defaults to `os.environ`.
