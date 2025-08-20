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
$toEmail = "mkim@indexiq.com,munawar.gani@ap.linedata.com,nitin.kamble@ap.linedata.com,index@indexiq.com,alerts@gravitas.co"
$errorEmail = "munawar.gani@ap.linedata.com,nitin.kamble@ap.linedata.com"
$fromEmail = "Alerts_Research@IndexIQ.com"

# AWS Secret Manager for Graph API
$secretName = "indexiq-graph-api-dev/credentials"
$region = "us-east-1"

# SQL Server
$connectionString = "Server=inviiqresearch-sqlserver-standard-dev.ckryme4eosdx.us-east-1.rds.amazonaws.com;Database=ResearchDWH;User Id=stonebranchuser;Password=Welcome@2025;TrustServerCertificate=True;"

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
# Graph API Email Functions
# ==============================
function Get-GraphToken {
    param ([string]$SecretName, [string]$Region)

    $response = Get-SECSecretValue -SecretId $SecretName -Region $Region
    $secret = $response.SecretString | ConvertFrom-Json

    $clientId = $secret.client_id
    $tenantId = $secret.tenant_id
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
# Main Loop
# ==============================
LogWrite("Job Start ***********************************************************")
SummaryLogWrite("$jobname Log Starts --------------------------------------------------------------------------------------------------")

while ($script:counter -le $script:exitcounter) {
    LogWrite("Starting counter - $script:counter")
    try {
        $runDate = Get-LastBusinessDay -Date (Get-Date) -DateFormat "yyyyMMdd"
        LogWrite("Run Date --> $runDate")

        # Get average returns
        $avgdata = Invoke-Sqlcmd -ConnectionString $connectionString -Query "EXEC GetTotallReturnStatData_Avrage_Updated" -QueryTimeout 0
       
		$avgtable = "<html><style> th {border:2px black solid !important} </style> <style> td {border:2px black solid !important} </style>
             <style> table {border:2px black solid !important} </style><table>"
            $avgtable += "<tr>"
            $avgtable += "<th>N</th>"
            $avgtable += "<th>maxRetPct</th>"
            $avgtable += "<th>minRetPct</th>"
            $avgtable += "</tr>"
            
            foreach ($row in $avgdata) {
                $avgtable += "<tr>"
                $avgtable += "<td>$($row.N)</td>"
                $avgtable += "<td>$($row.maxRetPct)</td>"
                $avgtable += "<td>$($row.minRetPct)</td>"
                $avgtable += "</tr>"
            }
            
            $avgtable += "</table></br></br>"


           $connectionString = "Server=inviiqresearch-sqlserver-standard-dev.ckryme4eosdx.us-east-1.rds.amazonaws.com;Database=ResearchDWH;User Id=stonebranchuser;Password=Welcome@2025;TrustServerCertificate=True;"

           $returndata = Invoke-Sqlcmd -ConnectionString $connectionString -Query "EXEC GetTotallReturnStatData_Updated" -QueryTimeout 0

           
            $returntable = "<table>"
            $returntable += "<tr>"
            $returntable += "<th>Ticker</th>"
            $returntable += "<th>DailyReturn</th>"
            $returntable += "<th>CreatedOn</th>"
            $returntable += "</tr>"
            
            foreach ($row in $returndata) {
                $returntable += "<tr>"
                $returntable += "<td>$($row.Ticker)</td>"
                $returntable += "<td>$($row.DailyReturn)</td>"
                $returntable += "<td>$($row.CreatedOn)</td>"
                $returntable += "</tr>"
            }
            
            $returntable += "</table></html>"

            $table =$avgtable+$returntable

        # Get Graph token and send email
        $accessToken = Get-GraphToken -SecretName $secretName -Region $region
        Send-GraphMail -From $fromEmail -To $toEmail -Subject "Market Returns Data Alert - $runDate" -BodyHtml $table -Token $accessToken

        LogWrite("Email sent successfully.")
    }
    catch {
        $errorMessage = $_.Exception.Message
        LogWrite("Exception Message: $errorMessage")
        SummaryLogWrite("Exception Message: $errorMessage")
        try {
            $accessToken = Get-GraphToken -SecretName $secretName -Region $region
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
