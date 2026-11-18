"""Create a consistent SQLite backup without overwriting an existing file."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3


def backup(source: Path, destination: Path) -> None:
    source = source.resolve(strict=True)
    destination = destination.absolute()
    if not source.is_file() or source == destination.resolve():
        raise ValueError('备份源必须是已有数据库，且不能与目标相同')
    # Exclusive creation prevents accidental overwrite, including concurrent runs.
    with destination.open('xb'):
        pass
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
            with closing(sqlite3.connect(destination)) as copy:
                original.backup(copy)
                result = copy.execute('PRAGMA integrity_check').fetchone()
                if result != ('ok',):
                    raise RuntimeError('备份完整性检查失败')
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='已有SQLite数据库')
    parser.add_argument('destination', type=Path, help='尚不存在的备份文件路径')
    args = parser.parse_args()
    backup(args.source, args.destination)
    print('备份完成，完整性检查通过：', args.destination)


if __name__ == '__main__':
    main()
