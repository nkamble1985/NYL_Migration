# ==============================
# Config
# ==============================
$Logfile = "c:\Logs\Log_ResearchDWH_Holdings_Stat.txt"
$SummaryLogfile = "c:\Logs\EXEC_HoldingsSummaryLog.txt"
$jobname = "ResearchDWH_Holdings_Stat"

$script:counter = 1
$script:exitcounter = 1
$timeInterval = 30 # seconds

# Recipients
$toEmail = "nitin_kamble@nylim.com,munawar_gani1@nylim.com"
$errorEmail = "nitin_kamble@nylim.com,munawar_gani1@nylim.com"
$fromEmail = "Alerts_IIQResearch@ntlab.newyorklife.com"

# AWS Secret Manager names
$graphSecretName = "indexiq-graph-api-dev/credentials"
$dbSecretName    = "dev/ResearchDWH/sqlserver"
$region = "us-east-1"

# ==============================
# Logging Functions
# ==============================
Function LogWrite {
    Param ([string]$logstring)
    $DateStr = Get-Date -Format "MM/dd/yyyy HH:mm:ss "
    Add-content $Logfile -value "$DateStr - $logstring"
}

Function SummaryLogWrite {
    Param ([string]$logstring)
    $DateStr = Get-Date -Format "MM/dd/yyyy HH:mm:ss "
    Add-content $SummaryLogfile -value "$DateStr - $logstring"
}

# ==============================
# Email Functions
# ==============================
function Get-GraphToken {
    param (
        [string]$SecretName,
        [string]$Region
    )

    $response = Get-SECSecretValue -SecretId $SecretName -Region $Region
    $secret   = $response.SecretString | ConvertFrom-Json

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
# Business Day Helper
# ==============================
function Get-LastBusinessDay {
    param (
        [DateTime]$Date = [DateTime]::Today,
        [String]$DateFormat
    )
    $Weekends = @([DayOfWeek]::Saturday, [DayOfWeek]::Sunday)
    $LastBusinessDay = $Date.AddDays(-1)
    while ($LastBusinessDay.DayOfWeek -in $Weekends) {
        $LastBusinessDay = $LastBusinessDay.AddDays(-1)
    }
    return $LastBusinessDay.ToString($DateFormat)
}

# ==============================
# Main Script
# ==============================
LogWrite("Job Start ***********************************************************")
SummaryLogWrite("$jobname Log Starts --------------------------------------------------------------------------------------------------")

while($script:counter -le $script:exitcounter) {
    LogWrite("Starting counter - $script:counter")
    try {
        $runDate = Get-LastBusinessDay -Date (Get-Date) -DateFormat "yyyyMMdd"
        LogWrite("Run Date --> $runDate")

        # Fetch DB secret from AWS
        $dbResponse = Get-SECSecretValue -SecretId $dbSecretName -Region $region
        $dbSecret   = $dbResponse.SecretString | ConvertFrom-Json
        $dbUser     = $dbSecret.username
        $dbPass     = $dbSecret.password
        $dbHost     = $dbSecret.host
        $dbName     = $dbSecret.database

        $connectionString = "Server=$dbHost;Database=$dbName;User Id=$dbUser;Password=$dbPass;TrustServerCertificate=True;"

        $avgdata = Invoke-Sqlcmd -ConnectionString $connectionString -Query "EXEC sp_getHoldingsForAlert" -QueryTimeout 0

        # Build HTML table
        $avgtable = "<html><style> th {border:2px black solid !important} </style> <style> td {border:2px black solid !important} </style>
             <style> table {border:2px black solid !important} </style><b>ReserchDWH - Holdings Refresh Counts</b></b><br><table>"
        $avgtable += "<tr><th>ReferenceId</th><th>source</th><th>ReferenceCode</th><th>Description</th><th>Date</th><th>Pwgt</th><th>N</th></tr>"
            
        foreach ($row in $avgdata) {
            $avgtable += "<tr>"
            $avgtable += "<td>$($row.ReferenceId)</td>"
            $avgtable += "<td>$($row.source)</td>"
            $avgtable += "<td>$($row.ReferenceCode)</td>"
            $avgtable += "<td>$($row.Description)</td>"
            $avgtable += "<td>$($row.Date)</td>"
            $avgtable += "<td>$($row.Pwgt)</td>"
            $avgtable += "<td>$($row.N)</td>"
            $avgtable += "</tr>"
        }
        $avgtable += "</table></br></br>"

        # Get Graph token from AWS Secrets Manager
        $accessToken = Get-GraphToken -SecretName $graphSecretName -Region $region

        # Send email
        Send-GraphMail -From $fromEmail -To $toEmail `
            -Subject "Holdings Data Alert - $runDate" `
            -BodyHtml $avgtable `
            -Token $accessToken

        LogWrite("Email sent successfully.")
    }
    catch {
        $errorMessage = $_.Exception.Message
        LogWrite("Exception Message: $errorMessage")
        SummaryLogWrite("Exception Message: $errorMessage")
        try {
            $accessToken = Get-GraphToken -SecretName $graphSecretName -Region $region
            Send-GraphMail -From $fromEmail -To $errorEmail `
                -Subject "ERROR: Holdings Data Alert - $runDate" `
                -BodyHtml "<b>Error Occurred:</b><br>$errorMessage" `
                -Token $accessToken
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
