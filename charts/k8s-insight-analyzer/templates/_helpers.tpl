{{- define "k8s-insight-analyzer.fullname" -}}
{{- printf "%s-%s" .Release.Name "k8s-insight-analyzer" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "k8s-insight-analyzer.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
app.kubernetes.io/managed-by: Helm
{{- end -}}
