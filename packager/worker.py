"""Run native analysis in a fresh process with an explicit input directory."""
import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('protocol', 'base_tables', 'effective_tables'))
    parser.add_argument('--analysis-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--apk24', type=Path)
    parser.add_argument('--data-work', type=Path)
    parser.add_argument('--stage-ratios', choices=('baseline', 'repaired'), default='baseline')
    args = parser.parse_args()
    os.environ['BH3_CLIENT19_ANALYSIS_DIR'] = str(args.analysis_dir.resolve())
    if args.stage == 'protocol':
        from server19_extract_protocol import extract
        result = extract()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'commands': len(result['commands']), 'schemas': len(result['schemas'])}))
    elif args.stage == 'effective_tables':
        if args.apk24 is None or args.data_work is None:
            parser.error('--apk24 and --data-work are required')
        from packager.tables import restore
        print(json.dumps(restore(args.apk24, args.data_work, args.output)))
    else:
        if args.apk24 is None:
            parser.error('--apk24 is required for base_tables')
        from server19_metadata_export import export
        result = export(args.output, args.apk24, (1, 9), 'cn', args.stage_ratios)
        print(json.dumps({'exported': sum('output_file' in row for row in result['files'])}))


if __name__ == '__main__':
    main()
