#!/usr/bin/env python3
"""Exercise the real no-TD receiver under USB mocks; no hardware access."""
import json
from pathlib import Path
import subprocess
from build_no_td_receiver import ROOT, OUT


def main():
    meta = json.loads((OUT / 'manifest.json').read_text())
    lib = Path(meta['library'])
    cmd = ['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
           '-I' + str(lib.parent.parent), '-I' + str(OUT),
           '-DISO_RECEIVER_SOURCE="' + str(OUT / 'receiver-source.c') + '"',
           str(ROOT / 'tests/no_td_window_test.c'), str(lib), '-framework', 'IOKit',
           '-framework', 'CoreFoundation', '-framework', 'Security', '-lobjc',
           '-o', str(OUT / 'no-td-window-test')]
    result = subprocess.run(cmd, text=True, capture_output=True)
    (OUT / 'validation-build.log').write_text(result.stdout + result.stderr)
    result.check_returncode()
    cases = []
    for mode in range(12):
        folder = OUT / 'validation' / str(mode)
        folder.mkdir(parents=True, exist_ok=False)
        result = subprocess.run([str(OUT / 'no-td-window-test'), str(folder / 'host.jsonl'),
                                 str(folder / 'native.txt'), str(mode)],
                                text=True, capture_output=True, timeout=8)
        cases.append(dict(mode=mode, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
        if result.returncode:
            raise RuntimeError(f'Mode {mode}: {result.stderr}')
    invalid = []
    for args in [[], ['--burst'], ['--receive-only', '--repeat', '2'],
                 ['--receive-only', '--packets', '959'],
                 ['--receive-only', '--packets', '960', '--trigger-delay-ms', '39'],
                 ['--empty-window', '--packets', '960', '--trigger-delay-ms', '40']]:
        destination = OUT / 'must-not-exist.jsonl'
        result = subprocess.run([str(OUT / 'iso-probe-no-td'), *args, '--log', str(destination)],
                                capture_output=True, text=True, timeout=8)
        assert result.returncode == 2 and not destination.exists()
        invalid.append(dict(args=args, exit_code=result.returncode))
    (OUT / 'validation.json').write_text(json.dumps(dict(passed=True, usb_accessed=False,
        build_command=cmd, mock_real_receiver_cases=cases, cli_rejections=invalid), indent=2) + '\n')
    print('12 real receiver mock cases and 6 CLI rejections passed; no USB access')


if __name__ == '__main__':
    main()
