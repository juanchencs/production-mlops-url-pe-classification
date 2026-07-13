# ---------------------------------------------------------------------------
# SNS topic for alarm notifications
# Subscribe via:
#   aws sns subscribe --topic-arn <ARN> --protocol email --notification-endpoint <EMAIL>
# ---------------------------------------------------------------------------
resource "aws_sns_topic" "alerts" {
  name = "mlscan-alerts"
}

# ---------------------------------------------------------------------------
# Alarms — malicious-rate spike (model drift signal)
# Fires when any single job has >70% of items flagged malicious.
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "malicious_spike_url" {
  alarm_name          = "mlscan-malicious-spike-url"
  alarm_description   = ">70% of a URL scan batch flagged malicious — possible model drift or real threat spike"
  namespace           = "MLScan"
  metric_name         = "MaliciousPct"
  dimensions          = { Service = "url" }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 70
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "malicious_spike_pe" {
  alarm_name          = "mlscan-malicious-spike-pe"
  alarm_description   = ">70% of a PE scan batch flagged malicious — possible model drift or real threat spike"
  namespace           = "MLScan"
  metric_name         = "MaliciousPct"
  dimensions          = { Service = "pe" }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 70
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

# ---------------------------------------------------------------------------
# Alarms — job errors
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "job_error_url" {
  alarm_name          = "mlscan-job-error-url"
  alarm_description   = "A URL scan job failed (JobError > 0)"
  namespace           = "MLScan"
  metric_name         = "JobError"
  dimensions          = { Service = "url" }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "job_error_pe" {
  alarm_name          = "mlscan-job-error-pe"
  alarm_description   = "A PE scan job failed (JobError > 0)"
  namespace           = "MLScan"
  metric_name         = "JobError"
  dimensions          = { Service = "pe" }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# ---------------------------------------------------------------------------
# Alarms — guardrail: quarantine events (any quarantine = immediate alert)
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "guardrail_quarantine_url" {
  alarm_name          = "mlscan-guardrail-quarantine-url"
  alarm_description   = "URL item quarantined — probability >= 0.95; high-confidence malicious detection"
  namespace           = "MLScan"
  metric_name         = "Quarantine"
  dimensions          = { Service = "url" }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "guardrail_quarantine_pe" {
  alarm_name          = "mlscan-guardrail-quarantine-pe"
  alarm_description   = "PE file quarantined — probability >= 0.95; file copied to s3://<bucket>/quarantine/pe/"
  namespace           = "MLScan"
  metric_name         = "Quarantine"
  dimensions          = { Service = "pe" }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# ---------------------------------------------------------------------------
# Alarms — guardrail: security alerts (>= 5 in 5 min window)
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "guardrail_security_alert_url" {
  alarm_name          = "mlscan-guardrail-security-alert-url"
  alarm_description   = ">= 5 URL security alerts in 5 min — probability 0.75-0.95; manual triage required"
  namespace           = "MLScan"
  metric_name         = "SecurityAlert"
  dimensions          = { Service = "url" }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 4
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "guardrail_security_alert_pe" {
  alarm_name          = "mlscan-guardrail-security-alert-pe"
  alarm_description   = ">= 5 PE security alerts in 5 min — probability 0.75-0.95; manual triage required"
  namespace           = "MLScan"
  metric_name         = "SecurityAlert"
  dimensions          = { Service = "pe" }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 4
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# ---------------------------------------------------------------------------
# CloudWatch Dashboard — one screen for both services
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_dashboard" "mlscan" {
  dashboard_name = "mlscan-overview"

  dashboard_body = jsonencode({
    widgets = [
      # ── Row 1: URL service ────────────────────────────────────────────────
      {
        type   = "metric"
        x = 0; y = 0; width = 6; height = 6
        properties = {
          title   = "URL — Score Distribution"
          view    = "timeSeries"
          stacked = false
          region  = var.aws_region
          period  = 300
          metrics = [
            ["MLScan", "Score", "Service", "url", { stat = "Average", label = "Mean" }],
            ["...", { stat = "p90", label = "p90" }],
            ["...", { stat = "Maximum", label = "Max" }],
          ]
          yAxis = { left = { min = 0, max = 100 } }
        }
      },
      {
        type   = "metric"
        x = 6; y = 0; width = 6; height = 6
        properties = {
          title   = "URL — Malicious % per Job"
          view    = "timeSeries"
          region  = var.aws_region
          period  = 300
          metrics = [
            ["MLScan", "MaliciousPct", "Service", "url", { stat = "Maximum", color = "#d62728", label = "Malicious %" }],
          ]
          annotations = {
            horizontal = [{ value = 70, label = "Drift alarm threshold", color = "#ff7f0e", fill = "above" }]
          }
          yAxis = { left = { min = 0, max = 100 } }
        }
      },
      {
        type   = "metric"
        x = 12; y = 0; width = 6; height = 6
        properties = {
          title   = "URL — Scan Latency (ms)"
          view    = "timeSeries"
          region  = var.aws_region
          period  = 300
          metrics = [
            ["MLScan", "ScanLatencyMs", "Service", "url", { stat = "Average", label = "Mean" }],
            ["...", { stat = "p99", label = "p99" }],
          ]
          yAxis = { left = { min = 0 } }
        }
      },
      {
        type   = "metric"
        x = 18; y = 0; width = 6; height = 6
        properties = {
          title   = "URL — Queue Depth & Job Duration"
          view    = "timeSeries"
          region  = var.aws_region
          period  = 300
          metrics = [
            ["MLScan", "JobQueueDepth",    "Service", "url", { stat = "Maximum", label = "Queue depth" }],
            ["MLScan", "JobDuration",      "Service", "url", { stat = "Average", label = "Avg job (s)", yAxis = "right" }],
            ["MLScan", "JobItemsProcessed","Service", "url", { stat = "Sum",     label = "Items processed", yAxis = "right" }],
          ]
        }
      },
      # ── Row 2: PE service ─────────────────────────────────────────────────
      {
        type   = "metric"
        x = 0; y = 6; width = 6; height = 6
        properties = {
          title   = "PE — Score Distribution"
          view    = "timeSeries"
          region  = var.aws_region
          period  = 300
          metrics = [
            ["MLScan", "Score", "Service", "pe", { stat = "Average", label = "Mean" }],
            ["...", { stat = "p90", label = "p90" }],
            ["...", { stat = "Maximum", label = "Max" }],
          ]
          yAxis = { left = { min = 0, max = 100 } }
        }
      },
      {
        type   = "metric"
        x = 6; y = 6; width = 6; height = 6
        properties = {
          title   = "PE — Malicious % per Job"
          view    = "timeSeries"
          region  = var.aws_region
          period  = 300
          metrics = [
            ["MLScan", "MaliciousPct", "Service", "pe", { stat = "Maximum", color = "#d62728", label = "Malicious %" }],
          ]
          annotations = {
            horizontal = [{ value = 70, label = "Drift alarm threshold", color = "#ff7f0e", fill = "above" }]
          }
          yAxis = { left = { min = 0, max = 100 } }
        }
      },
      {
        type   = "metric"
        x = 12; y = 6; width = 6; height = 6
        properties = {
          title   = "PE — Scan Latency (ms)"
          view    = "timeSeries"
          region  = var.aws_region
          period  = 300
          metrics = [
            ["MLScan", "ScanLatencyMs", "Service", "pe", { stat = "Average", label = "Mean" }],
            ["...", { stat = "p99", label = "p99" }],
          ]
          yAxis = { left = { min = 0 } }
        }
      },
      {
        type   = "metric"
        x = 18; y = 6; width = 6; height = 6
        properties = {
          title   = "PE — Queue Depth & Job Duration"
          view    = "timeSeries"
          region  = var.aws_region
          period  = 300
          metrics = [
            ["MLScan", "JobQueueDepth",    "Service", "pe", { stat = "Maximum", label = "Queue depth" }],
            ["MLScan", "JobDuration",      "Service", "pe", { stat = "Average", label = "Avg job (s)", yAxis = "right" }],
            ["MLScan", "JobItemsProcessed","Service", "pe", { stat = "Sum",     label = "Items processed", yAxis = "right" }],
          ]
        }
      },
      # ── Row 3: Errors + alarm panel ───────────────────────────────────────
      {
        type   = "metric"
        x = 0; y = 12; width = 12; height = 6
        properties = {
          title   = "Job Errors (URL + PE)"
          view    = "timeSeries"
          region  = var.aws_region
          period  = 300
          metrics = [
            ["MLScan", "JobError", "Service", "url", { stat = "Sum", color = "#d62728", label = "URL errors" }],
            ["MLScan", "JobError", "Service", "pe",  { stat = "Sum", color = "#ff7f0e", label = "PE errors" }],
          ]
          yAxis = { left = { min = 0 } }
        }
      },
      {
        type   = "alarm"
        x = 12; y = 12; width = 12; height = 6
        properties = {
          title  = "Active Alarms"
          alarms = [
            aws_cloudwatch_metric_alarm.malicious_spike_url.arn,
            aws_cloudwatch_metric_alarm.malicious_spike_pe.arn,
            aws_cloudwatch_metric_alarm.job_error_url.arn,
            aws_cloudwatch_metric_alarm.job_error_pe.arn,
            aws_cloudwatch_metric_alarm.guardrail_quarantine_url.arn,
            aws_cloudwatch_metric_alarm.guardrail_quarantine_pe.arn,
            aws_cloudwatch_metric_alarm.guardrail_security_alert_url.arn,
            aws_cloudwatch_metric_alarm.guardrail_security_alert_pe.arn,
          ]
        }
      },
      # ── Row 4: Decision Guardrails verdict distribution ───────────────────
      {
        type   = "metric"
        x = 0; y = 18; width = 12; height = 6
        properties = {
          title   = "URL — Guardrail Verdict Counts"
          view    = "timeSeries"
          stacked = true
          region  = var.aws_region
          period  = 300
          metrics = [
            ["MLScan", "Quarantine",    "Service", "url", { stat = "Sum", color = "#d62728", label = "Quarantine (>=0.95)" }],
            ["MLScan", "SecurityAlert", "Service", "url", { stat = "Sum", color = "#ff7f0e", label = "Alert (0.75-0.95)" }],
            ["MLScan", "ManualReview",  "Service", "url", { stat = "Sum", color = "#f7dc6f", label = "Manual Review (0.30-0.75)" }],
          ]
          yAxis = { left = { min = 0 } }
        }
      },
      {
        type   = "metric"
        x = 12; y = 18; width = 12; height = 6
        properties = {
          title   = "PE — Guardrail Verdict Counts"
          view    = "timeSeries"
          stacked = true
          region  = var.aws_region
          period  = 300
          metrics = [
            ["MLScan", "Quarantine",    "Service", "pe", { stat = "Sum", color = "#d62728", label = "Quarantine (>=0.95)" }],
            ["MLScan", "SecurityAlert", "Service", "pe", { stat = "Sum", color = "#ff7f0e", label = "Alert (0.75-0.95)" }],
            ["MLScan", "ManualReview",  "Service", "pe", { stat = "Sum", color = "#f7dc6f", label = "Manual Review (0.30-0.75)" }],
          ]
          yAxis = { left = { min = 0 } }
        }
      },
    ]
  })
}
