"""Database maintenance: python -m app.manage_database status|upgrade."""
import argparse
import json
from app.db import engine
from app.schema_versions import schema_status, upgrade_schema


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('status', 'upgrade'))
    args = parser.parse_args()
    if args.command == 'upgrade':
        upgrade_schema(engine)
    print(json.dumps(schema_status(engine)))


if __name__ == '__main__':
    main()
