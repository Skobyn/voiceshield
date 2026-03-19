terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

variable "project_id" {
  default = "apex-internal-apps"
}

variable "region" {
  default = "us-central1"
}

variable "image_url" {
  default = "gcr.io/apex-internal-apps/voiceshield:latest"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_cloud_run_v2_service" "voiceshield" {
  name     = "voiceshield"
  location = var.region

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }

    containers {
      image = var.image_url

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "USE_FIRESTORE"
        value = "true"
      }

      # Secrets injected via Secret Manager
      env {
        name = "DEEPGRAM_API_KEY"
        value_source {
          secret_key_ref {
            secret  = "voiceshield-deepgram-key"
            version = "latest"
          }
        }
      }

      env {
        name = "ANTHROPIC_API_KEY"
        value_source {
          secret_key_ref {
            secret  = "voiceshield-anthropic-key"
            version = "latest"
          }
        }
      }

      env {
        name = "TWILIO_ACCOUNT_SID"
        value_source {
          secret_key_ref {
            secret  = "voiceshield-twilio-sid"
            version = "latest"
          }
        }
      }

      env {
        name = "TWILIO_AUTH_TOKEN"
        value_source {
          secret_key_ref {
            secret  = "voiceshield-twilio-token"
            version = "latest"
          }
        }
      }

      env {
        name = "SENDGRID_API_KEY"
        value_source {
          secret_key_ref {
            secret  = "voiceshield-sendgrid-key"
            version = "latest"
          }
        }
      }
    }
  }
}

# Allow unauthenticated access (webhook endpoints need this)
resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.voiceshield.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

output "url" {
  value = google_cloud_run_v2_service.voiceshield.uri
}
