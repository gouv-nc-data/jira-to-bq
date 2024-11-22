locals {
  parent_folder_id         = 658965356947 # production folder
  secret-managment-project = "prj-dinum-p-secret-mgnt-aaf4"
  templates_project        = "prj-dinum-data-templates-66aa"
  workload_bucket          = "bucket-prj-dinum-data-templates-66aa"
  sa_roles = [
    "roles/bigquery.dataEditor",
    "roles/bigquery.user",
    "roles/dataproc.editor",
    "roles/dataproc.worker",
    "roles/storage.objectViewer",
    "roles/iam.serviceAccountUser",
    "roles/cloudscheduler.jobRunner"
  ]
  api_to_activate = [
    "secretmanager.googleapis.com",
    "cloudscheduler.googleapis.com",
    "dataproc.googleapis.com"
  ]
  safe-ds-name = substr(lower(replace(var.dataset_name, "_", "-")), 0, 24)
}

resource "google_service_account" "service_account" {
  account_id   = "sa-jira2bq-${local.safe-ds-name}"
  display_name = "Service Account created by terraform for ${var.project_id}"
  project      = var.project_id
}

resource "google_project_iam_member" "bigquery_editor_bindings" {
  for_each = toset(local.sa_roles)
  project  = var.project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.service_account.email}"
}

resource "google_project_iam_custom_role" "dataproc-custom-role" {
  project     = var.project_id
  role_id     = "spark_sched_custom_role_${var.dataset_name}"
  title       = "Dataproc Custom Role"
  description = "Role custom pour pouvoir créer des job dataproc depuis scheduler"
  permissions = ["iam.serviceAccounts.actAs", "dataproc.workflowTemplates.instantiate"]
}

resource "google_project_iam_member" "dataflow_custom_worker_bindings" {
  project    = var.project_id
  role       = "projects/${var.project_id}/roles/${google_project_iam_custom_role.dataproc-custom-role.role_id}"
  member     = "serviceAccount:${google_service_account.service_account.email}"
  depends_on = [google_project_iam_custom_role.dataproc-custom-role]
}

# je ne comprends pas cette ressource, ce devrait etre pour autoriser un compte principal à utiliser un SA 
resource "google_service_account_iam_member" "gce-default-account-iam" {
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.service_account.email}"
  service_account_id = google_service_account.service_account.name
}


####
# Dataproc
####

resource "google_storage_bucket_iam_member" "access_to_script" {
  bucket = local.workload_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.service_account.email}"
}

resource "google_project_iam_member" "service_account_bindings_artifact_r" {
  project = local.templates_project
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.service_account.email}"
}

resource "google_project_service" "activate_api" {
  for_each = toset(local.api_to_activate)
  project  = var.project_id
  service  = each.key
}

data "google_secret_manager_secret_version" "jira-bq-key-secret" {
  project = local.secret-managment-project
  secret  = "jira-token-bigquery"
}

resource "google_cloud_scheduler_job" "job" {
  project          = var.project_id
  name             = "jira2bq-job-${local.safe-ds-name}"
  schedule         = var.schedule
  time_zone        = "Pacific/Noumea"
  attempt_deadline = "320s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "https://dataproc.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/batches/"
    oauth_token {
      service_account_email = google_service_account.service_account.email
    }
    body = base64encode(
      jsonencode(
        {
          "pysparkBatch" : {
            "args" : [
              "--jira-project=${var.jira_project}",
              "--gcp-project=${var.project_id}",
              "--bq-dataset=${var.dataset_name}",
              "--jira-token=${data.google_secret_manager_secret_version.jira-bq-key-secret.secret_data}"
            ],
            "mainPythonFileUri" : "gs://bucket-prj-dinum-data-templates-66aa/jira_to_bigquery.py"
          },
          "runtimeConfig" : {
            "containerImage" : "${var.region}-docker.pkg.dev/${local.templates_project}/templates/jira-to-bq:latest",
            "version" : "2.1",
            "properties" : {
              "spark.executor.instances" : "2",
              "spark.driver.cores" : "4",
              "spark.driver.memory" : "9600m",
              "spark.executor.cores" : "4",
              "spark.executor.memory" : "9600m",
              "spark.dynamicAllocation.executorAllocationRatio" : "0.3",
              "spark.hadoop.fs.gs.inputstream.support.gzip.encoding.enable" : "true"
            }
          },
          "environmentConfig" : {
            "executionConfig" : {
              "serviceAccount" : google_service_account.service_account.email,
              # "subnetworkUri" : "subnet-for-vpn"
            }
          }
        }
      )
    )
  }
  # depends_on = [google_project_service.cloudschedulerapi]
}

###############################
# Supervision
###############################
resource "google_monitoring_alert_policy" "errors" {
  display_name = "Errors in logs alert policy on ${var.dataset_name}"
  project      = var.project_id
  combiner     = "OR"
  conditions {
    display_name = "Error condition"
    condition_matched_log {
      filter = "severity=ERROR AND resource.type=\"cloud_dataproc_cluster\" and protoPayload.methodName != \"google.cloud.dataproc.v1.ClusterController.CreateCluster\""
    }
  }

  notification_channels = var.notification_channels
  alert_strategy {
    notification_rate_limit {
      period = "300s"
    }
    auto_close = "86400s" # 1 jour
  }
}