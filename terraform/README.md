# module terraform jira to bigquery

```
module "jira-bq-dataproc" {
  source                = "git::https://github.com/gouv-nc-data/jira-to-bq//terraform?ref=main"
  project_id            = module.dinum-exp-datawarehouse.project_id
  jira_project          = "DATA"
  dataset_name          = "data_dataproc"
  schedule              = "15 4 1 1 *"       # “At 04:15 on day-of-month 1 in January.”
  generation_id         = "1732252359879692" # tag de version dans le bucket
  notification_channels = module.dinum-exp-datawarehouse.notification_channels
}
```