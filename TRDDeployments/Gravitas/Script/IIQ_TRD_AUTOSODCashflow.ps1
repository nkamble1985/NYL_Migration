# ================================================
# AUTO SOD PowerShell Script - DB + Graph API creds from AWS
# Includes recursive retry logic
# ================================================

# Load AWS Tools for PowerShell
Import-Module AWSPowerShell

# -------------------------
# Log paths
# -------------------------
$Logfile = "C:\Gravitas\Logs\Execute_AUTO_SODLog.txt"
$SummaryLogfile = "C:\Gravitas\Logs\EquitizerSummaryLog.txt"
$jobname = "Execute_AUTO_SOD"

$fileFolderPath = "C:\Gravitas\SOD CASH MACRO ARCHIVE\"
$fileNamePattern = "_SODCash_LIVE.xlsx"

$toEmail = "nitin_kamble@nylim.com"
$errorEmail = "nitin_kamble@nylim.com"

# -------------------------
# Logging functions
# -------------------------
Function SummaryLogWrite {
    Param ([string]$logstring)
    $DateStr = Get-Date -Format "MM/dd/yyyy HH:mm:ss "
    Add-Content $SummaryLogfile -Value "$DateStr - $logstring"
}

Function LogWrite {
    Param ([string]$logstring)
    $DateStr = Get-Date -Format "MM/dd/yyyy HH:mm:ss"
    Add-Content $Logfile -Value "$DateStr - $logstring"
}

# -------------------------
# Get last business day
# -------------------------
function Get-LastBusinessDay {
    [CmdletBinding()]
    param (
        [System.DateTime]$Date = [System.DateTime]::Today,
        [System.String]$DateFormat
    )

    $Weekends = @([System.DayOfWeek]::Saturday, [System.DayOfWeek]::Sunday)
    $LastBusinessDay = $Date

    while ($LastBusinessDay.DayOfWeek -in $Weekends) {
        $LastBusinessDay = $LastBusinessDay.AddDays(-1)
    }

    return $LastBusinessDay.ToString($DateFormat)
}

# -------------------------
# Fetch DB credentials from AWS Secrets Manager
# -------------------------
try {
    $secretName = "dev/Equitizer/sqlserver"
    $region = "us-east-1"

    $secretValue = Get-SECSecretValue -SecretId $secretName -Region $region
    $secretJson = $secretValue.SecretString | ConvertFrom-Json

    $dbUser = $secretJson.username
    $dbPassword = $secretJson.password
    $dbHost = $secretJson.host
    $dbName = $secretJson.database

    $connectionString = "Server=$dbHost;Database=$dbName;User ID=$dbUser;Password=$dbPassword;Trusted_Connection=False;Connection Timeout=300"
}
catch {
    $errorMessage = "Failed to fetch DB credentials from AWS Secrets Manager: $($_.Exception.Message)"
    LogWrite($errorMessage)
    Send-ToEmail -recipientEmail $errorEmail -emailMessage $errorMessage -emailSubject "AUTO SOD - DB Credential Error"
    exit
}

# -------------------------
# Fetch Graph API credentials from AWS Secrets Manager
# -------------------------
try {
    $graphSecretName = "indexiq-graph-api-dev/credentials"
    $graphSecretValue = Get-SECSecretValue -SecretId $graphSecretName -Region $region
    $graphSecret = $graphSecretValue.SecretString | ConvertFrom-Json

    $clientId = $graphSecret.client_id
    $tenantId = $graphSecret.tenant_id
    $clientSecret = $graphSecret.client_secret
}
catch {
    $errorMessage = "Failed to fetch Graph API credentials: $($_.Exception.Message)"
    LogWrite($errorMessage)
    Send-ToEmail -recipientEmail $errorEmail -emailMessage $errorMessage -emailSubject "AUTO SOD - Graph API Credential Error"
    exit
}

# -------------------------
# Graph API email functions
# -------------------------
function Get-GraphToken {
    $body = @{
        client_id     = $clientId
        scope         = "https://graph.microsoft.com/.default"
        client_secret = $clientSecret
        grant_type    = "client_credentials"
    }

    $response = Invoke-RestMethod -Method Post `
                -Uri "https://login.microsoftonline.com/$tenantId/oauth2/v2.0/token" `
                -ContentType "application/x-www-form-urlencoded" `
                -Body $body
    return $response.access_token
}

function Send-ToEmail {
    param (
        [string]$recipientEmail,
        [string]$emailMessage,
        [string]$emailSubject
    )

    try {
        $token = Get-GraphToken

        $mailBody = @{
            message = @{
                subject = $emailSubject
                body = @{
                    contentType = "Text"
                    content     = $emailMessage
                }
                toRecipients = @(@{emailAddress = @{address = $recipientEmail}})
            }
            saveToSentItems = "true"
        } | ConvertTo-Json -Depth 10

        Invoke-RestMethod -Uri "https://graph.microsoft.com/v1.0/users/Alerts_IIQApps@ntlab.newyorklife.com/sendMail" `
                          -Headers @{Authorization = "Bearer $token"} `
                          -Method POST -Body $mailBody -ContentType "application/json"
    }
    catch {
        $errorMessage = $_.Exception.Message
        LogWrite("Send-ToEmail (Graph) - Exception: $errorMessage")
    }
}

# -------------------------
# Call stored procedure function
# -------------------------
function CallProc {
    param ([datetime]$runDate)

    try {
        $connection = New-Object System.Data.SqlClient.SqlConnection $connectionString
        $storedProcName = "sp_CheckDataLoad"
        $command = New-Object System.Data.SqlClient.SqlCommand $storedProcName, $connection
        $command.CommandType = [System.Data.CommandType]::StoredProcedure
        $command.Parameters.AddWithValue("@DataDate", $runDate)

        $connection.Open()
        $reader = $command.ExecuteReader()

        $Status = ""
        $Action = ""
        $Message = ""

        if ($reader.HasRows) {
            while ($reader.Read()) {
                $Status = $reader["Status"]
                $Action = $reader["Action"]
                $Message = $reader["Message"]
            }
        } else {
            LogWrite("No rows returned from SP.")
        }

        $reader.Close()

        return @{
            Status = $Status
            Action = $Action
            Message = $Message
        }
    } 
    catch {
        LogWrite("Error in CallProc: $($_.Exception.Message)")
    } 
    finally {
        if ($connection.State -ne 'Closed') {
            $connection.Close()
        }
    }
}

# -------------------------
# Main Execution
# -------------------------
LogWrite("Job Start ***********************************************************")
SummaryLogWrite("$jobname Log Starts ------------------------------------------------------------------------------------------------------------------------------")

try {
    $runDate = Get-LastBusinessDay -Date (Get-Date) -DateFormat "yyyy-MM-dd HH:mm:ss"
    $filedatetime = Get-LastBusinessDay -Date (Get-Date) -DateFormat "MM.dd.yyyy hh.mm"
    $ExecutablePath = "C:\Deployments\AUTOSOD\AUTOSODCashflow.exe"

    # Initialize counters for retry loop
    $script:counter = 1
    $script:exitcounter = 3  # max retries
    $timeInterval = 240      # 4 minutes between retries

    while ($script:counter -le $script:exitcounter) {
        LogWrite("Retry Counter: $script:counter")

        $result = CallProc $runDate
        LogWrite("Status=$($result.Status), Action=$($result.Action), Message=$($result.Message)")

        if ($result.Status -eq 'Success' -and $result.Action -eq 'Completed') {
            LogWrite("AUTO SOD Execution Starting  --> run date $runDate")
            & $ExecutablePath $runDate

            $filePath = $fileFolderPath + $filedatetime + $fileNamePattern
            if (Test-Path $filePath -PathType Leaf) {
                LogWrite("AUTO SOD Cash File Generated at $filePath")
                Send-ToEmail -recipientEmail $toEmail -emailMessage "AUTO SOD Cash File Generated at $filePath." -emailSubject "AUTO SOD - File Generated Successfully"
                break  # Exit retry loop after success
            } else {
                LogWrite("AUTO SOD - File not generated, retrying...")
            }
        } else {
            LogWrite("Status not ready for execution. Waiting $timeInterval seconds before next attempt...")
            Send-ToEmail -recipientEmail $toEmail -emailMessage " Retry #$script:counter: AUTO SOD Status=$($result.Status), Action=$($result.Action). Waiting $timeInterval seconds before next attempt." -emailSubject "AUTO SOD - Retry in Progress"
        }

        $script:counter += 1
        Start-Sleep -Seconds $timeInterval
    }

    if ($script:counter -gt $script:exitcounter) {
        LogWrite("AUTO SOD - Retry attempts exceeded maximum limit.")
        Send-ToEmail -recipientEmail $toEmail -emailMessage "AUTO SOD retry failed after maximum attempts. Check logs." -emailSubject "AUTO SOD - Retry Failed"
    }
}
catch {
    $errorMessage = $_.Exception.Message
    LogWrite("Exception Message: $errorMessage")
    SummaryLogWrite("Exception Message: $errorMessage")
    Send-ToEmail -recipientEmail $errorEmail -emailMessage $errorMessage -emailSubject "AUTO SOD - Execution Error"
}

LogWrite("Job End ***********************************************************")
SummaryLogWrite("$jobname Log Ends ------------------------------------------------------------------------------------------------------------------------------")
