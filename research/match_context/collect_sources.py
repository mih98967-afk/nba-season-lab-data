"""Read-only public-data intake, no credentials/private profiles or data publishing."""
from __future__ import annotations
import argparse,csv,datetime,gzip,hashlib,json,pathlib,shutil,subprocess,urllib.request
import pyarrow.parquet as pq
KINDS=[('nba_stats_player_boxscores','player_boxscores_{}.csv'),('nba_stats_schedules','nba_schedule_{}.csv.gz'),('nba_stats_game_rosters','game_rosters_{}.csv'),('nba_stats_injury_report','injury_report_{}.parquet')]

def collect(years,root):
    root.mkdir(parents=True,exist_ok=True);manifest=[];converted=[]
    for year in years:
        for tag,stem in KINDS:
            name=stem.format(year);url=f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/{tag}/{name}'
            item={'url':url,'fetched_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'NBA-Season-Lab/noncommercial-research'})
                with urllib.request.urlopen(req,timeout=50) as response:content=response.read(80000001)
                if len(content)>80000000:raise ValueError('Source size limit')
                p=root/name;p.write_bytes(content);item.update(file=name,bytes=len(content),sha256=hashlib.sha256(content).hexdigest(),status='retrieved')
                if name.endswith('.parquet'):
                    table=pq.read_table(p);dest=p.with_suffix('.csv.gz')
                    with gzip.open(dest,'wt',newline='',encoding='utf8') as f:
                        w=csv.DictWriter(f,fieldnames=table.column_names);w.writeheader()
                        for batch in table.to_batches(max_chunksize=10000):w.writerows(batch.to_pylist())
                    converted.append({'source_file':name,'derived_file':dest.name,'rows':table.num_rows,'schema':str(table.schema),'source_sha256':item['sha256'],'derived_sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
            except Exception as exc:item.update(status='unavailable',error=str(exc)[:300])
            manifest.append(item)
    (root/'injury_conversion_manifest.json').write_text(json.dumps(converted,indent=2)+'\n')
    return manifest

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=pathlib.Path,default=pathlib.Path('match-context-artifact'));a=ap.parse_args();root=a.root;root.mkdir(parents=True,exist_ok=True)
    for folder in ('src','data'):
        if pathlib.Path(folder).is_dir():shutil.copytree(folder,root/folder,dirs_exist_ok=True)
    try:(root/'source_commit.txt').write_text(subprocess.check_output(['git','rev-parse','HEAD'],text=True))
    except subprocess.CalledProcessError:(root/'source_commit.txt').write_text('local-source-bundle\n')
    historical=collect((2024,2025,2026),root/'upstream');(root/'upstream_manifest.json').write_text(json.dumps(historical,indent=2)+'\n')
    current=collect((2027,),root/'current');(root/'current'/'manifest.json').write_text(json.dumps(current,indent=2)+'\n')
    print(json.dumps({'historical':historical,'current_coverage_probe':current},indent=2))
if __name__=='__main__':main()
