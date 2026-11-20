#!/usr/bin/env python3
"""Build deterministic Kodi Omega/Piers indexes and packages for GitHub Pages."""
import argparse
import gzip
import hashlib
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


CHANNELS = ('omega', 'piers')
EXCLUDED_PARTS = {
    '.git',
    '.github',
    '.pytest_cache',
    '.tox',
    '.mypy_cache',
    '__pycache__',
    'tests',
}
EXCLUDED_NAMES = {'AGENTS.md', 'AI_USAGE.md', 'coverage.xml', '.coverage'}
ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def addon_metadata(source):
    root = ET.parse(source / 'addon.xml').getroot()
    return root.attrib['id'], root.attrib['version']


def source_files(source):
    for path in sorted(source.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if relative.name in EXCLUDED_NAMES or relative.suffix == '.pyc':
            continue
        yield path, relative


def write_zip(source, destination, extra_files=()):
    addon_id, _ = addon_metadata(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, relative in source_files(source):
            info = zipfile.ZipInfo((Path(addon_id) / relative).as_posix(), ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
        for path, relative in sorted(extra_files, key=lambda item: item[1].as_posix()):
            info = zipfile.ZipInfo((Path(addon_id) / relative).as_posix(), ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def sha256(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(path.name + '.sha256').write_text(f'{digest}  {path.name}\n', encoding='ascii')


def build_index(addons, channel_dir):
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<addons>']
    for source in addons:
        addon_xml = (source / 'addon.xml').read_text(encoding='utf-8').strip()
        if addon_xml.startswith('<?xml'):
            addon_xml = addon_xml.split('?>', 1)[1].lstrip()
        xml.append(addon_xml)
    xml.append('</addons>')
    content = ('\n'.join(xml) + '\n').encode('utf-8')
    index = channel_dir / 'addons.xml'
    index.write_bytes(content)
    with (channel_dir / 'addons.xml.gz').open('wb') as output:
        with gzip.GzipFile(filename='', mode='wb', fileobj=output, mtime=0) as zipped:
            zipped.write(content)
    sha256(channel_dir / 'addons.xml.gz')


def build(root, installer, helper, trakt, upnext, providers, skin, dependencies, output):
    repository = root / 'repository.duskmate'
    addons = (repository, installer, helper, trakt, upnext, *providers, skin, *dependencies)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    repo_id, repo_version = addon_metadata(repository)
    for channel in CHANNELS:
        channel_dir = output / channel
        zip_root = channel_dir / 'zips'
        for source in addons[1:]:
            addon_id, version = addon_metadata(source)
            package = zip_root / addon_id / f'{addon_id}-{version}.zip'
            write_zip(source, package)
            sha256(package)

    installer_id, installer_version = addon_metadata(installer)
    installer_bootstrap = output / f'{installer_id}-{installer_version}.zip'
    write_zip(installer, installer_bootstrap)
    sha256(installer_bootstrap)

    bootstrap = output / f'{repo_id}-{repo_version}.zip'
    write_zip(repository, bootstrap)
    sha256(bootstrap)

    for channel in CHANNELS:
        channel_dir = output / channel
        zip_root = channel_dir / 'zips'
        repository_package = zip_root / repo_id / f'{repo_id}-{repo_version}.zip'
        write_zip(repository, repository_package)
        sha256(repository_package)
        build_index(addons, channel_dir)

    (output / 'index.html').write_text(
        '<!doctype html><meta charset="utf-8"><title>Duskmate repository</title>'
        '<h1>Duskmate Kodi repository</h1>'
        f'<p><a href="{repo_id}-{repo_version}.zip">Install {repo_id} {repo_version}</a></p>'
        '<p>This repository contains no player packs or streaming-provider add-ons.</p>\n',
        encoding='utf-8',
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--installer', type=Path, required=True)
    parser.add_argument('--helper', type=Path, required=True)
    parser.add_argument('--trakt', type=Path, required=True)
    parser.add_argument('--upnext', type=Path, required=True)
    parser.add_argument('--provider', type=Path, action='append', default=[])
    parser.add_argument('--skin', type=Path, required=True)
    parser.add_argument('--dependency', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, default=Path('dist'))
    args = parser.parse_args()
    build(
        Path(__file__).resolve().parents[1],
        args.installer.resolve(),
        args.helper.resolve(),
        args.trakt.resolve(),
        args.upnext.resolve(),
        tuple(path.resolve() for path in args.provider),
        args.skin.resolve(),
        tuple(path.resolve() for path in args.dependency),
        args.output.resolve(),
    )


if __name__ == '__main__':
    main()
