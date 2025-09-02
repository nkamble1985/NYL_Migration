# ==============================
# Config
# ==============================
$Logfile        = "C:\Gravitas\Logs\Execute_CashMergerLog.txt"
$SummaryLogfile = "C:\Gravitas\Logs\EquitizerSummaryLog.txt"

$fileFolderPath  = "C:\Gravitas\SharedFiles\DailyCash\"  # Output folder
$fileNamePattern = "Daily Cash_"
$errorEmail      = "nitin_kamble@nylim.com"
$region          = "us-east-1"  # AWS region for secrets
$toEmail         = "nitin_kamble@nylim.com"  # Recipient email

# ==============================
# Functions
# ==============================
function LogWrite {
    param([string]$logMsg)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "$timestamp : $logMsg"
    Write-Output $entry
    Add-Content -Path $Logfile -Value $entry
}

function SummaryLogWrite {
    param([string]$logMsg)
    Add-Content -Path $SummaryLogfile -Value $logMsg
}

function Send-ToEmail {
    param(
        [string]$recipientEmail,   # Recipient
        [string]$emailMessage,     # Email body
        [string]$emailSubject,     # Subject
        [string]$fromEmail = $emailId  # Sender; defaults to $emailId
    )

    try {
        # Acquire OAuth Token
        $tokenUrl = "https://login.microsoftonline.com/$tenantId/oauth2/v2.0/token"
        $body = @{
            client_id     = $clientId
            scope         = "https://graph.microsoft.com/.default"
            client_secret = $clientSecret
            grant_type    = "client_credentials"
        }

        $tokenResponse = Invoke-RestMethod -Method Post -Uri $tokenUrl -Body $body
        $accessToken = $tokenResponse.access_token

        # Prepare Email Payload
        $mailBody = @{
            message = @{
                subject = $emailSubject
                body    = @{
                    contentType = "Text"
                    content     = $emailMessage
                }
                toRecipients = @(@{ emailAddress = @{ address = $recipientEmail } })
                from = @{ emailAddress = @{ address = $fromEmail } }  # sender
            }
            saveToSentItems = "true"
        } | ConvertTo-Json -Depth 4

        # Send Email via Graph API
        $graphUri = "https://graph.microsoft.com/v1.0/users/$fromEmail/sendMail"

        Invoke-RestMethod -Method Post -Uri $graphUri -Headers @{ Authorization = "Bearer $accessToken" } -Body $mailBody -ContentType "application/json"

        LogWrite "Email sent successfully from '$fromEmail' to '$recipientEmail' with subject '$emailSubject'."
    }
    catch {
        $errorMsg = "Failed to send email: $($_.Exception.Message)"
        LogWrite $errorMsg
        SummaryLogWrite $errorMsg
    }
}

# ==============================
# Fetch Graph API Credentials
# ==============================
try {
    $graphSecretName = "indexiq-graph-api-dev/credentials"
    $graphSecretValue = Get-SECSecretValue -SecretId $graphSecretName -Region $region
    $graphSecret = $graphSecretValue.SecretString | ConvertFrom-Json

    $clientId     = $graphSecret.client_id
    $tenantId     = $graphSecret.tenant_id
    $clientSecret = $graphSecret.client_secret   # For Graph API authentication
    $emailId      = $graphSecret.email_Id       # Email sender
    LogWrite "Successfully fetched Graph API credentials and email ID."
}
catch {
    $errorMessage = "Failed to fetch Graph API credentials: $($_.Exception.Message)"
    LogWrite $errorMessage
    Send-ToEmail -recipientEmail $errorEmail -emailMessage $errorMessage -emailSubject "AUTO SOD - Graph API Credential Error"
    exit
}

# ==============================
# Run CashMerger.exe
# ==============================
try {
    $days = 0
    $runDate = Get-LastBusinessDay -Date (Get-Date).AddDays($days) -DateFormat "yyyy-MM-dd HH:mm:ss"
    $filedatetime = Get-LastBusinessDay -Date (Get-Date).AddDays($days) -DateFormat "MM.dd.yyyy hh.mm"

    $ExecutablePath = "C:\Deployments\CashMergerProd\CashMerger\CashMerger.exe"
    & $ExecutablePath $runDate

    LogWrite "Daily Cash Execution End  --> for run date $runDate"
}
catch {
    $errorMessage = $_.Exception.Message
    LogWrite "Exception Message: $errorMessage"
    SummaryLogWrite "Exception Message: $errorMessage"
    Send-ToEmail -recipientEmail $toEmail -emailMessage $errorMessage -emailSubject "AUTO SOD - CashMerger Execution Error"
    exit
}

# ==============================
# Daily Cash File Check
# ==============================
$filePath = $fileFolderPath + $fileNamePattern + $filedatetime + ".xlsx"
LogWrite "Daily Cash file watcher path  --> $filePath"

if (Test-Path $filePath -PathType Leaf) {
    LogWrite "Daily Cash file generated at $filePath."
    Send-ToEmail -recipientEmail $toEmail `
                 -emailMessage "Daily Cash File Generated at $filePath." `
                 -emailSubject "Daily Cash - File Generated Successfully"
} else {
    $failMsg = "Daily Cash - Failed to generate file"
    LogWrite $failMsg
    Send-ToEmail -recipientEmail $toEmail `
                 -emailMessage $failMsg `
                 -emailSubject "Daily Cash - Failed to generate file"
}
