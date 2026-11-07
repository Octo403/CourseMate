"""Package current runtime source and Windows ECS scripts without local data."""
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=root/'dist/ecs-windows/AnotherMe-ECS-Windows-Source.zip')
    args = parser.parse_args()
    paths = [root/'pyproject.toml', root/'README.md',
             root/'scripts/run_hosted_server.py']
    for directory in (root/'src', root/'scripts/deploy/windows', root/'docs'):
        paths.extend(path for path in directory.rglob('*') if path.is_file()
                     and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo'))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, 'w', compression=ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            archive.write(path, path.relative_to(root).as_posix())
        archive.writestr('START-HERE.txt',
            'AnotherMe Windows Server ECS source deployment\r\n'
            'Install Python 3.13 x64 and extract this ZIP to C:\\AnotherMe.\r\n'
            'Open PowerShell as Administrator:\r\n'
            '  cd C:\\AnotherMe\r\n'
            '  powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\deploy\\windows\\Install-Server.ps1 -PublicIp YOUR_ECS_PUBLIC_IP\r\n'
            'Read docs/ECS_WINDOWS.md for security groups, HTTPS, visitor isolation and maintenance.\r\n'
            'This ZIP contains source and scripts; Python, dependencies and Caddy download during setup.\r\n')
    with ZipFile(args.output) as archive:
        damaged = archive.testzip()
        if damaged:
            raise RuntimeError('Unreadable ZIP member: '+damaged)
        print(f'{args.output}\n{len(archive.namelist())} files; {args.output.stat().st_size} bytes')


if __name__ == '__main__':
    main()
