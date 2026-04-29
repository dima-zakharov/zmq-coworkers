use reqwest::Client;

pub struct MetricsReporter {
    client: Client,
    endpoint: String,
}

impl MetricsReporter {
    pub fn new(url: &str) -> Self {
        Self {
            client: Client::new(),
            endpoint: url.to_string(),
        }
    }

    pub async fn report_stats(&self, tasks_sent: u64, in_flight: usize) {
        let line = format!(
            "coordinator_metrics,node=main_node tasks_sent={}u,in_flight={}u",
            tasks_sent, in_flight
        );

        let _ = self.client
            .post(&self.endpoint)
            .body(line)
            .send()
            .await;
    }
}