"""Build a complete scientific data/weights checkpoint, excluding repository code."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, re, zipfile
from pathlib import Path

ARCHIVE_NAME='NBA_MODEL_RESEARCH_CHECKPOINT_20261117.zip'
CODE_SUFFIXES={'.py','.pyc','.md','.sh','.log','.txt'}

def digest(blob):return hashlib.sha256(blob).hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--workspace',type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument('--output',type=Path)
    ap.add_argument('--research-commit',default='PENDING_FINAL_RESEARCH_SHA')
    a=ap.parse_args();root=a.workspace.resolve()
    if a.research_commit!='PENDING_FINAL_RESEARCH_SHA' and not re.fullmatch('[0-9a-f]{40}',a.research_commit):
        raise ValueError('Use a full verified research SHA or the explicit pending placeholder')
    dest=a.output or root/'artifacts'/ARCHIVE_NAME;dest.parent.mkdir(parents=True,exist_ok=True)
    files={};groups={}
    def add(path,group,allow_dereference=False):
        if not path.is_file() or (path.is_symlink() and not allow_dereference):raise ValueError('MISSING_OR_SYMLINK:'+str(path))
        name=path.relative_to(root).as_posix()
        if any(x in path.parts for x in ('private','__pycache__','.git')) or '/common/' in name or path.suffix in CODE_SUFFIXES:
            raise ValueError('EXCLUDED_CODE_PRIVATE_OR_CACHE:'+name)
        if name in files:raise ValueError('DUPLICATE_ARCHIVE_PATH:'+name)
        files[name]=path.read_bytes();groups[group]=groups.get(group,0)+1
    # Immutable original scientific package: data, fitted weights, JSON evidence.
    for path in sorted((root/'research_base').rglob('*')):
        if not path.is_file():continue
        if path.suffix in CODE_SUFFIXES or '__pycache__' in path.parts or path.name=='source_bundle.tar.xz':continue
        add(path,'original_research_noncode')
    for relative in ('research_extension/fresh_20261117/source/current',
                     'research_extension/fresh_20261117/source/data',
                     'research_extension/prospective/current_snapshot/data'):
        for path in sorted((root/relative).iterdir()):
            if not path.is_file() or path.is_symlink():raise ValueError('UNEXPECTED_SOURCE_PATH:'+str(path))
            add(path,'new_raw_sources')
    for name in ('feature_frame.pkl','future_feature_frame.pkl'):
        add(root/'research_extension/fresh_20261117'/name,'fresh_feature_frames')
    for name in ('participation/results/historical_calibration_predictions.csv.gz',
                 'position/results/general_predictions.csv.gz',
                 'position/results/opponent_feature_diagnostics.csv.gz',
                 'recency/predictions.csv.gz'):
        add(root/'research_extension'/name,'new_per_row_results')
    for name in ('position/results/FUTURE_POSITION_MAPPING.json',
                 'prospective_20261117/forecasts.json',
                 'prospective_20261117/COMMITMENT.json',
                 'recency/refitted_day_ewma_mean.pkl',
                 'recency/REFIT_REPORT.json',
                 'fresh_20261117/source/upstream_manifest.json'):
        add(root/'research_extension'/name,'additional_frozen_model_evidence')
    # Materialize only this verified historical-source alias. ZIP contains no links.
    alias=root/'research_extension/fresh_20261117/source/upstream'
    original=root/'research_base/source/upstream'
    if alias.is_symlink() and alias.resolve()!=original.resolve():raise ValueError('UNTRUSTED_UPSTREAM_ALIAS')
    for path in sorted(alias.iterdir()):
        if not path.is_file() or path.suffix in CODE_SUFFIXES:raise ValueError('UNEXPECTED_UPSTREAM_FILE')
        reference=original/path.name
        if not reference.is_file() or digest(path.read_bytes())!=digest(reference.read_bytes()):raise ValueError('UPSTREAM_ALIAS_BYTES_DIFFER')
        add(path,'materialized_fresh_historical_sources',allow_dereference=True)
    note='''# NBA Season Lab — полный научный checkpoint от 17 ноября 2026

**Исходные снимки, веса и построчные результаты. Это НЕ Firebase Hosting ZIP.**

Код, протоколы и новые итоговые отчёты находятся в существующем PR178:
https://github.com/mih98967-afk/nba-season-lab-data/pull/178
Ветка: `research/match-context-distribution-20261116`.
Точный commit с кодом: `__RESEARCH_COMMIT__`.
Если остался `PENDING_FINAL_RESEARCH_SHA`, привязка к финальному коммиту ещё не заполнена.

## Что сохранено

- `research_base/`: исходные исторические и текущие source snapshots исследования 16 ноября, три полных model bundles, прежние JSON-отчёты, baseline feature frame и неизменные 1741 frozen-прогноз.
- `research_extension/`: свежие источники 17 ноября и feature frames; точные публичные evidence snapshots; четыре файла построчных результатов; позиционный mapping; новые 334 paired-прогноза с commitment; веса и отчёт нового recency-кандидата.
- Исторический `fresh_20261117/source/upstream` материализован обычными файлами; абсолютных symlinks в ZIP нет.

Пути сохранены для распаковки в корень существующего checkout. Новые источники не заменяют старые: каждый эксперимент использует собственный snapshot. Веса и данные доступны без повторного скачивания прежнего handoff. Старый полный research ZIP остаётся дополнительным оригиналом; его SHA-256: `3428b9fda239e84ebb62b88a0f46c88400c9f5dd9356b153e2f58ccdea8aff9b`.

## Проверка и восстановление

`MANIFEST_SHA256.json` содержит размер и SHA-256 каждого включённого файла, кроме самого manifest. Прежний `research_base/PACKAGE_MANIFEST.json` описывает исходный пакет, включая код и tar-дубликат, которые здесь намеренно отсутствуют; для проверки этого ZIP используйте корневой manifest.

Python, shell-скрипты и Markdown-кодовая документация берутся из указанного GitHub-коммита. Если runner ожидает код в `research_base/research/match_context`, используйте код checkout `research/match_context` через поддерживаемый fallback либо восстановите относительную ссылку на него. `NBA_RESEARCH_BASE` должен указывать на распакованный `research_base`.

Архив не содержит личных данных владельца, git-каталога, кода сайта, Hosting-релиза или крупных промежуточных caches. Источники NBA-derived не подтверждают Sports.ru credited FP. Сам архив не внедряет модель: scientific research и production разделены.
'''.replace('__RESEARCH_COMMIT__',a.research_commit)
    scientific_count=len(files)
    files['00_README_FIRST.md']=note.encode('utf-8')
    manifest={'schema':'nba-complete-scientific-checkpoint-v1','created_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
              'repository':'mih98967-afk/nba-season-lab-data','existing_PR':178,'research_commit':a.research_commit,
              'contains_data_weights_and_results':True,'contains_git_backed_code':False,'not_hosting_archive':True,
              'private_data_included':False,'scientific_files':scientific_count,'groups':groups,
              'files':[{'path':name,'bytes':len(blob),'sha256':digest(blob)} for name,blob in sorted(files.items())]}
    files['MANIFEST_SHA256.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    temporary=dest.with_suffix('.tmp.zip')
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,blob in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,11,17,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,blob,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    with zipfile.ZipFile(temporary) as z:
        if z.testzip() is not None:raise ValueError('ZIP_CRC_FAILED')
        if set(z.namelist())!=set(files):raise ValueError('ZIP_CONTENT_SET_CHANGED')
        for item in manifest['files']:
            blob=z.read(item['path'])
            if len(blob)!=item['bytes'] or digest(blob)!=item['sha256']:raise ValueError('ZIP_MANIFEST_MISMATCH')
    if temporary.stat().st_size>=50*1024*1024:raise ValueError('CHECKPOINT_EXCEEDS_50_MIB')
    temporary.replace(dest)
    print(json.dumps({'path':str(dest.resolve()),'research_commit':a.research_commit,'scientific_files':scientific_count,
                      'groups':groups,'metadata_files':2,'zip_entries':len(files),
                      'uncompressed_bytes':sum(len(b) for b in files.values()),'zip_bytes':dest.stat().st_size,
                      'zip_sha256':digest(dest.read_bytes()),'crc':'PASS','manifest_verified_files':len(manifest['files'])},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
