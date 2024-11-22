variable "project_id" {
  type        = string
  description = "id du projet"
}

variable "region" {
  type    = string
  default = "europe-west1"
}

variable "schedule" {
  type        = string
  description = "expression cron de schedule du job"
}

variable "dataset_name" {
  type        = string
  description = "nom du projet"
}

variable "jira_project" {
  type        = string
  description = "nom du projet jira ex : DATA"
}

variable "notification_channels" {
  type        = list(string)
  description = "canal de notification pour les alertes sur dataproc"
}

# variable "exclude" {
#   type        = list
#   description = "liste des keys à ne pas migrer"
#   default     = ""
# }

variable "mode" {
  type        = string
  description = "type d'upload sur bigquery"
  default     = "overwrite"
}
