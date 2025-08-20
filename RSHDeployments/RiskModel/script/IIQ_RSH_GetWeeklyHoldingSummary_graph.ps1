# ==============================
# Config
# ==============================
$Logfile = "C:\Logs\Log_EXEC_WeeklyHoldingSummary.txt"
$SummaryLogfile = "C:\Logs\EXEC_WeeklyHoldingSummaryLog.txt"
$jobname = "EXEC_Holdings"

$script:counter = 1
$script:exitcounter = 1
$timeInterval = 30 # seconds

# Email / Graph API
$toEmail = "nitin_kamble@nylim.com"
$errorEmail = "nitin_kamble@nylim.com"
$fromEmail = "Alerts_IIQResearch@ntlab.newyorklife.com"  # Verified mailbox
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
# Graph API Functions
# ==============================
function Get-GraphToken {
    param ([string]$SecretName, [string]$Region)
    $response = Get-SECSecretValue -SecretId $SecretName -Region $Region
    $secret = $response.SecretString | ConvertFrom-Json

    $body = @{
        client_id     = $secret.client_id
        scope         = "https://graph.microsoft.com/.default"
        client_secret = $secret.client_secret
        grant_type    = "client_credentials"
    }

    $tokenResponse = Invoke-RestMethod -Method Post -Uri "https://login.microsoftonline.com/$($secret.tenant_id)/oauth2/v2.0/token" -Body $body
    return $tokenResponse.access_token
}

function Send-GraphMail {
    param ([string]$From, [string]$To, [string]$Subject, [string]$BodyHtml, [string]$Token)
    $recipients = @()
    foreach ($addr in $To.Split(",")) { $recipients += @{ emailAddress = @{ address = $addr.Trim() } } }

    $email = @{
        message = @{
            subject      = $Subject
            body         = @{ contentType="HTML"; content=$BodyHtml }
            toRecipients = $recipients
        }
        saveToSentItems = "true"
    } | ConvertTo-Json -Depth 10

    $uri = "https://graph.microsoft.com/v1.0/users/$From/sendMail"
    Invoke-RestMethod -Method Post -Uri $uri -Headers @{ Authorization = "Bearer $Token"; "Content-Type" = "application/json" } -Body $email
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

        # Get SQL Data
        $returndata = Invoke-Sqlcmd -ConnectionString $connectionString -Query "EXEC sp_WeeklyHoldingSummary" -QueryTimeout 0

        # Build HTML Table with red highlights for zero
        $returntable = "<html>
                 <body>
                 <table style='border-collapse: collapse; border: 2px solid black; width: 100%;'>
                 <tr>
                     <th style='border: 2px solid black; width: 150px; text-align: center;'>RecordDate</th>
                     <th style='border: 2px solid black; width: 100px; text-align: center;'>All</th>
                     <th style='border: 2px solid black; width: 100px; text-align: center;'>AWGBLGC</th>
                     <th style='border: 2px solid black; width: 100px; text-align: center;'>AWGBLGV</th>
                     <th style='border: 2px solid black; width: 100px; text-align: center;'>AWGBLVC</th>
                     <th style='border: 2px solid black; width: 100px; text-align: center;'>H_SDL</th>
                     <th style='border: 2px solid black; width: 100px; text-align: center;'>AWIC</th>
                 </tr>"


            $connectionString = "Server=inviiqresearch-sqlserver-standard-dev.ckryme4eosdx.us-east-1.rds.amazonaws.com;Database=ResearchDWH;User Id=stonebranchuser;Password=Welcome@2025;TrustServerCertificate=True;"

			$returndata = Invoke-Sqlcmd -ConnectionString $connectionString -Query "EXEC sp_WeeklyHoldingSummary" -QueryTimeout 0

			#$returndata = Invoke-Sqlcmd -ServerInstance "inviiqresearch-sqlserver-standard-dev.ckryme4eosdx.us-east-1.rds.amazonaws.com" -Database "ResearchDWH" -Query "EXEC sp_WeeklyHoldingSummary" -QueryTimeout 0 
			
			foreach ($row in $returndata) {
				$returntable += "<tr>"
				
				# Check each value and apply the red background if it is zero
				$returntable += "<td style='border: 2px solid black; width: 150px; text-align: center; background-color: $(if ($row.RecordDate -eq 0) {'red'} else {'transparent'})'>"
				$returntable += "$($row.RecordDate)</td>"
				
				$returntable += "<td style='border: 2px solid black; width: 100px; text-align: center; background-color: $(if ($row.All -eq 0) {'red'} else {'transparent'})'>"
				$returntable += "$($row.All)</td>"
				
				$returntable += "<td style='border: 2px solid black; width: 100px; text-align: center; background-color: $(if ($row.AWGBLGC -eq 0) {'red'} else {'transparent'})'>"
				$returntable += "$($row.AWGBLGC)</td>"
				
				$returntable += "<td style='border: 2px solid black; width: 100px; text-align: center; background-color: $(if ($row.AWGBLGV -eq 0) {'red'} else {'transparent'})'>"
				$returntable += "$($row.AWGBLGV)</td>"
				
				$returntable += "<td style='border: 2px solid black; width: 100px; text-align: center; background-color: $(if ($row.AWGBLVC -eq 0) {'red'} else {'transparent'})'>"
				$returntable += "$($row.AWGBLVC)</td>"
				
				$returntable += "<td style='border: 2px solid black; width: 100px; text-align: center; background-color: $(if ($row.H_SDL -eq 0) {'red'} else {'transparent'})'>"
				$returntable += "$($row.H_SDL)</td>"
				
				$returntable += "<td style='border: 2px solid black; width: 100px; text-align: center; background-color: $(if ($row.AWIC -eq 0) {'red'} else {'transparent'})'>"
				$returntable += "$($row.AWIC)</td>"
				
				$returntable += "</tr>"
			}
			
			$returntable += "</table></body></html>"

        # Send Email via Graph API
        $accessToken = Get-GraphToken -SecretName $secretName -Region $region
        Send-GraphMail -From $fromEmail -To $toEmail -Subject "Weekly Holding Summary - $runDate" -BodyHtml $returntable -Token $accessToken

        LogWrite("Email sent successfully.")
    }
    catch {
        $errorMessage = $_.Exception.Message
        LogWrite("Exception Message: $errorMessage")
        SummaryLogWrite("Exception Message: $errorMessage")
        try {
            $accessToken = Get-GraphToken -SecretName $secretName -Region $region
            Send-GraphMail -From $fromEmail -To $errorEmail -Subject "ERROR: Weekly Holding Summary - $runDate" -BodyHtml "<b>Error Occurred:</b><br>$errorMessage" -Token $accessToken
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
