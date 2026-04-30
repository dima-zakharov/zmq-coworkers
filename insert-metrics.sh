# Get the current time in seconds
T=$(date +%s)

curl -d "
worker_task_processed_value,lang=python value=10 $((T-240))
worker_task_processed_value,lang=python value=50 $((T-180))
worker_task_processed_value,lang=python value=30 $((T-120))
worker_task_processed_value,lang=python value=80 $((T-60))
worker_task_processed_value,lang=python value=40 $T
" http://127.0.0.1:8428/write