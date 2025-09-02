# ==============================
# Config
# ==============================
$Logfile        = "C:\Gravitas\Logs\Execute_PriceRec_SODLog.txt"
$SummaryLogfile = "C:\Gravitas\Logs\EquitizerSummaryLog.txt"
$jobname        = "Execute_PriceRec_SOD"

$errorEmail     = "nitin_kamble@nylim.com"
$region         = "us-east-1"  # AWS region for secrets
$toEmail        = "nitin_kamble@nylim.com"  # Recipient email

$outputFolder   = "C:\Gravitas\SharedFiles\PriceRec\"  # Output folder
$filePrefix     = "Price_Rec_"

# ==============================
# Functions
# ==============================
function LogWrite {
    param([string]$logstring)
    $DateStr = Get-Date -Format "MM/dd/yyyy HH:mm:ss"
    Add-Content $Logfile -Value "$DateStr - $logstring"
}

function SummaryLogWrite {
    param([string]$logstring)
    $DateStr = Get-Date -Format "MM/dd/yyyy HH:mm:ss"
    Add-Content $SummaryLogfile -Value "$DateStr - $logstring"
}

function Get-LastBusinessDay {
    [CmdletBinding()]
    param (
        [Parameter(Position = 1)]
        [System.DateTime]$Date = [System.DateTime]::Today,
        [Parameter(Position = 2)]
        [System.String]$DateFormat
    )

    $Weekends = @([System.DayOfWeek]::Saturday, [System.DayOfWeek]::Sunday)
    $LastBusinessDay = $Date

    while ($Weekends -contains $LastBusinessDay.DayOfWeek) {
        $LastBusinessDay = $LastBusinessDay.AddDays(-1)
    }

    return $LastBusinessDay.ToString($DateFormat)
}

function Send-ToEmail {
    param(
        [string]$recipientEmail,
        [string]$emailMessage,
        [string]$emailSubject,
        [string]$fromEmail = $emailId  # Defaults to sender from Secrets
    )

    try {
        $tokenUrl = "https://login.microsoftonline.com/$tenantId/oauth2/v2.0/token"
        $body = @{
            client_id     = $clientId
            scope         = "https://graph.microsoft.com/.default"
            client_secret = $clientSecret
            grant_type    = "client_credentials"
        }

        $tokenResponse = Invoke-RestMethod -Method Post -Uri $tokenUrl -Body $body
        $accessToken = $tokenResponse.access_token

        $mailBody = @{
            message = @{
                subject = $emailSubject
                body    = @{
                    contentType = "Text"
                    content     = $emailMessage
                }
                toRecipients = @(@{ emailAddress = @{ address = $recipientEmail } })
                from = @{ emailAddress = @{ address = $fromEmail } }
            }
            saveToSentItems = "true"
        } | ConvertTo-Json -Depth 4

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
    $clientSecret = $graphSecret.client_secret
    $emailId      = $graphSecret.email_Id
    LogWrite "Successfully fetched Graph API credentials and email ID."
}
catch {
    $errorMessage = "Failed to fetch Graph API credentials: $($_.Exception.Message)"
    LogWrite $errorMessage
    Send-ToEmail -recipientEmail $errorEmail -emailMessage $errorMessage -emailSubject "$jobname - Graph API Credential Error"
    exit
}

# ==============================
# Main Script Execution
# ==============================
LogWrite "Job Start ***********************************************************"
SummaryLogWrite "$jobname Log Starts ------------------------------------------------------------------------------------------------------------------------------"

Try {
    $days = 0
    $runDate = Get-LastBusinessDay -Date (Get-Date).AddDays($days) -DateFormat "yyyy-MM-dd HH:mm:ss"
    $filedatetime = Get-LastBusinessDay -Date (Get-Date).AddDays($days) -DateFormat "MM.dd.yyyy HH.mm"

    $ExecutablePath = "C:\Deployments\PriceRecMergerProd\PriceRecMerger\PriceRecMerger.exe"
    & $ExecutablePath $runDate

    LogWrite "PriceRec SOD Execution End  --> for run date $runDate"

    # ==============================
    # Check if output file exists
    # ==============================
    $filePath = $outputFolder + $filePrefix + $filedatetime + ".xlsx"
    LogWrite "Checking output file path --> $filePath"

    if (Test-Path $filePath -PathType Leaf) {
        LogWrite "PriceRec SOD file generated at $filePath."
        Send-ToEmail -recipientEmail $toEmail `
                     -emailMessage "PriceRec SOD executed successfully and file generated at $filePath." `
                     -emailSubject "$jobname - File Generated Successfully"
    } else {
        $failMsg = "PriceRec SOD execution completed but file not found at $filePath"
        LogWrite $failMsg
        Send-ToEmail -recipientEmail $toEmail `
                     -emailMessage $failMsg `
                     -emailSubject "$jobname - File Not Found"
    }
}
Catch {
    $errorMessage = $_.Exception.Message
    LogWrite "Exception Message: $errorMessage"
    SummaryLogWrite "Exception Message: $errorMessage"
    Send-ToEmail -recipientEmail $toEmail `
                 -emailMessage $errorMessage `
                 -emailSubject "$jobname - Execution Error"
}

LogWrite "Job End ***********************************************************"
SummaryLogWrite "$jobname Log Ends ------------------------------------------------------------------------------------------------------------------------------"
