# ==============================
# Config
# ==============================
$Logfile = "C:\Logs\Log_EXEC_Holdings.txt"
$SummaryLogfile = "C:\Logs\EXEC_HoldingsSummaryLog.txt"
$jobname = "EXEC_Holdings"

$script:counter = 1
$script:exitcounter = 1
$timeInterval = 30 # seconds

# Email Details
$toEmail = "nitin_kamble@nylim.com" #"mkim@indexiq.com,munawar.gani@ap.linedata.com,nitin.kamble@ap.linedata.com,index@indexiq.com,alerts@gravitas.co"
$errorEmail = "nitin_kamble@nylim.com"
$fromEmail = "Alerts_IIQResearch@ntlab.newyorklife.com"

# AWS Secret Manager
$graphSecretName = "indexiq-graph-api-dev/credentials"
$dbSecretName    = "dev/ResearchDWH/sqlserver"
$region = "us-east-1"

# ==============================
# Logging Functions
# ==============================
function LogWrite { Param([string]$logstring) $DateStr = Get-Date -Format "MM/dd/yyyy HH:mm:ss "; Add-Content $Logfile -Value "$DateStr - $logstring" }
function SummaryLogWrite { Param([string]$logstring) $DateStr = Get-Date -Format "MM/dd/yyyy HH:mm:ss "; Add-Content $SummaryLogfile -Value "$DateStr - $logstring" }

# ==============================
# Business Day Helper
# ==============================
function Get-LastBusinessDay {
    param ([DateTime]$Date = [DateTime]::Today, [string]$DateFormat)
    $Weekends = @([DayOfWeek]::Saturday, [DayOfWeek]::Sunday)
    $LastBusinessDay = $Date.AddDays(-1)
    while ($LastBusinessDay.DayOfWeek -in $Weekends) { $LastBusinessDay = $LastBusinessDay.AddDays(-1) }
    return $LastBusinessDay.ToString($DateFormat)
}

# ==============================
# Secret Manager Helpers
# ==============================
function Get-DbConnectionString {
    param ([string]$SecretName, [string]$Region)

    $response = Get-SECSecretValue -SecretId $SecretName -Region $Region
    $secret = $response.SecretString | ConvertFrom-Json

    $server   = $secret.host
    $database = $secret.database
    $user     = $secret.username
    $password = $secret.password

    return "Server=$server;Database=$database;User Id=$user;Password=$password;TrustServerCertificate=True;"
}

function Get-GraphToken {
    param ([string]$SecretName, [string]$Region)

    $response = Get-SECSecretValue -SecretId $SecretName -Region $Region
    $secret = $response.SecretString | ConvertFrom-Json

    $clientId     = $secret.client_id
    $tenantId     = $secret.tenant_id
    $clientSecret = $secret.client_secret

    $body = @{
        client_id     = $clientId
        scope         = "https://graph.microsoft.com/.default"
        client_secret = $clientSecret
        grant_type    = "client_credentials"
    }

    $tokenResponse = Invoke-RestMethod -Method Post `
        -Uri "https://login.microsoftonline.com/$tenantId/oauth2/v2.0/token" `
        -Body $body

    return $tokenResponse.access_token
}

# ==============================
# Graph Mail Sender
# ==============================
function Send-GraphMail {
    param (
        [string]$From,
        [string]$To,
        [string]$Subject,
        [string]$BodyHtml,
        [string]$Token
    )

    $recipients = @()
    foreach ($addr in $To.Split(",")) {
        $recipients += @{ emailAddress = @{ address = $addr.Trim() } }
    }

    $email = @{
        message = @{
            subject = $Subject
            body = @{
                contentType = "HTML"
                content     = $BodyHtml
            }
            toRecipients = $recipients
        }
        saveToSentItems = "true"
    } | ConvertTo-Json -Depth 10

    $uri = "https://graph.microsoft.com/v1.0/users/$From/sendMail"

    Invoke-RestMethod -Method Post -Uri $uri `
        -Headers @{ Authorization = "Bearer $Token"; "Content-Type" = "application/json" } `
        -Body $email
}

# ==============================
# Main Loop
# ==============================
LogWrite("Job Start ***********************************************************")
SummaryLogWrite("$jobname Log Starts --------------------------------------------------------------------------------------------------")

while ($script:counter -le $script:exitcounter) {
    LogWrite("Starting counter - $script:counter")
    try {
        $runDate = Get-LastBusinessDay -Date (Get-Date) -DateFormat "yyyyMMdd"
        LogWrite("Run Date --> $runDate")

        # Get DB connection string from Secrets Manager
        $connectionString = Get-DbConnectionString -SecretName $dbSecretName -Region $region

        # Get average returns
        $avgdata = Invoke-Sqlcmd -ConnectionString $connectionString -Query "EXEC GetTotallReturnStatData_Avrage_Updated" -QueryTimeout 0
       
        $avgtable = "<html><style> th {border:2px black solid !important} </style> <style> td {border:2px black solid !important} </style>
             <style> table {border:2px black solid !important} </style><table>"
        $avgtable += "<tr><th>N</th><th>maxRetPct</th><th>minRetPct</th></tr>"
        foreach ($row in $avgdata) {
            $avgtable += "<tr><td>$($row.N)</td><td>$($row.maxRetPct)</td><td>$($row.minRetPct)</td></tr>"
        }
        $avgtable += "</table></br></br>"

        # Get detailed returns
        $returndata = Invoke-Sqlcmd -ConnectionString $connectionString -Query "EXEC GetTotallReturnStatData_Updated" -QueryTimeout 0
        $returntable = "<table><tr><th>Ticker</th><th>DailyReturn</th><th>CreatedOn</th></tr>"
        foreach ($row in $returndata) {
            $returntable += "<tr><td>$($row.Ticker)</td><td>$($row.DailyReturn)</td><td>$($row.CreatedOn)</td></tr>"
        }
        $returntable += "</table></html>"

        $table = $avgtable + $returntable

        # Get Graph token and send email
        $accessToken = Get-GraphToken -SecretName $graphSecretName -Region $region
        Send-GraphMail -From $fromEmail -To $toEmail -Subject "Market Returns Data Alert - $runDate" -BodyHtml $table -Token $accessToken

        LogWrite("Email sent successfully.")
    }
    catch {
        $errorMessage = $_.Exception.Message
        LogWrite("Exception Message: $errorMessage")
        SummaryLogWrite("Exception Message: $errorMessage")
        try {
            $accessToken = Get-GraphToken -SecretName $graphSecretName -Region $region
            Send-GraphMail -From $fromEmail -To $errorEmail -Subject "ERROR: Market Returns Data Alert - $runDate" -BodyHtml "<b>Error Occurred:</b><br>$errorMessage" -Token $accessToken
        } catch {
            LogWrite("Failed to send error email: $($_.Exception.Message)")
        }
    }

    Start-Sleep -Seconds $timeInterval
    LogWrite("Ending counter - $script:counter")
    $script:counter += 1
}

LogWrite("Job End ***********************************************************")
SummaryLogWrite("$jobname Log Ends --------------------------------------------------------------------------------------------------")
