"""Optional 2026/27 evidence intake. No inferred DNP and no production writes."""
import csv, datetime, gzip, hashlib, json, pathlib, urllib.request
import pyarrow.parquet as pq

def main():
    root=pathlib.Path('match-context-artifact/current');root.mkdir(parents=True,exist_ok=True)
    templates=[('nba_stats_player_boxscores','player_boxscores_2027.csv'),('nba_stats_schedules','nba_schedule_2027.csv.gz'),('nba_stats_game_rosters','game_rosters_2027.csv'),('nba_stats_injury_report','injury_report_2027.parquet')]
    manifest=[]
    for tag,name in templates:
        url=f'https://github.com/sportsdataverse/sportsdataverse-data/releases/download/{tag}/{name}'
        row={'url':url,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'NBA-Season-Lab/noncommercial-research'})
            with urllib.request.urlopen(req,timeout=45) as response:raw=response.read(80000001)
            if len(raw)>80000000:raise ValueError('Source size limit')
            path=root/name;path.write_bytes(raw);row.update(status='retrieved',file=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
            if name.endswith('.parquet'):
                table=pq.read_table(path);dest=path.with_suffix('.csv.gz')
                with gzip.open(dest,'wt',newline='',encoding='utf8') as f:
                    w=csv.DictWriter(f,fieldnames=table.column_names);w.writeheader()
                    for batch in table.to_batches(max_chunksize=10000):w.writerows(batch.to_pylist())
                row.update(converted_file=dest.name,rows=table.num_rows,converted_sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
        except Exception as exc:row.update(status='unavailable',error=str(exc)[:300])
        manifest.append(row)
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
