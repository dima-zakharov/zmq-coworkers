

curl -s -G 'http://localhost:8428/api/v1/query' \
    --data-urlencode 'query=worker_task_processed' | jq
    
curl -s -G 'http://localhost:8428/api/v1/query' \
    --data-urlencode 'query=count_samples(worker_task_processed[1h])' | jq '.data.result[0].value[1]'    

curl -s -G 'http://localhost:8428/api/v1/export' \
     -d 'match[]={__name__="worker_task_processed"}' | jq -s 'map(.values | length) | add'
     
     
     
     curl -s http://localhost:8428/metrics | grep -E 'vm_rows_inserted_total{type="influx"}|vm_rows_ignored_total{type="influx"}'
