# Log file paths
$Logfile = "C:\Gravitas\Logs\Execute_CashMergerLog.txt"
$SummaryLogfile = "C:\Gravitas\Logs\EquitizerSummaryLog.txt"
$jobname = "Execute_CashMerger"

# SMTP details

$errorMessage = ""

# Function to write to the summary log
Function SummaryLogWrite {
    Param ([string]$logstring)
    $DateStr = Get-Date -Format "MM/dd/yyyy HH:mm:ss"
    Add-content $SummaryLogfile -value "$DateStr - $logstring"
}

# Function to write to the log
Function LogWrite {
    Param ([string]$logstring)
    $DateStr = Get-Date -Format "MM/dd/yyyy HH:mm:ss"
    Add-content $Logfile -value "$DateStr - $logstring"
}

# Function to get the last business day
function Get-LastBusinessDay {
    [CmdletBinding()]
    param (
        [Parameter(Position = 1)]
        [System.DateTime]$Date = [System.DateTime]::Today,
        [Parameter(Position = 2)]
        [System.String]$DateFormat
    )

    $Weekends = @([System.DayOfWeek]::Saturday, [System.DayOfWeek]::Sunday)
    $LastBusinessDay = $Date.AddDays(0)

    while ($LastBusinessDay.DayOfWeek -in $Weekends) {
        $LastBusinessDay = $LastBusinessDay.AddDays(0)
    }

    return $LastBusinessDay.ToString($DateFormat)
}

# Logging job start
LogWrite("Job Start ***********************************************************")
SummaryLogWrite("$jobname Log Starts ------------------------------------------------------------------------------------------------------------------------------")

# Loop after the defined interval to check if file exists

        try {
            $days = -1
            $runDate = Get-LastBusinessDay -Date (Get-Date).AddDays($days) -DateFormat "yyyy-MM-dd HH:mm:ss"
            $filedatetime = Get-LastBusinessDay -Date (Get-Date).AddDays($days) -DateFormat "MM.dd.yyyy hh.mm"

            $ExecutablePath = "C:\Deployments\CashMergerProd\CashMerger\CashMerger.exe"
            & $ExecutablePath $runDate

            LogWrite("Daily Cash Execution End  --> for run date $runDate")
        } catch {
            $errorMessage = $($_.Exception.Message)
            LogWrite("Exception Message: $errorMessage")
            SummaryLogWrite("Exception Message: $errorMessage")
        }



# Logging job end
LogWrite("Job End ***********************************************************")
SummaryLogWrite("$jobname Log Ends ------------------------------------------------------------------------------------------------------------------------------")
