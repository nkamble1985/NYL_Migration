# Log file paths
$Logfile = "C:\Gravitas\Logs\Execute_InKind_SODLog.txt"
$SummaryLogfile = "C:\Gravitas\Logs\EquitizerSummaryLog.txt"
$jobname = "Execute_InKind_SOD"

$errorMessage = ""
# Function to be used for logging summary
Function SummaryLogWrite {
    Param ([string]$logstring)
    $DateStr = Get-Date -Format "MM/dd/yyyy HH:mm:ss"
    Add-Content $SummaryLogfile -Value "$DateStr - $logstring"
}

# Function to be used for logging
Function LogWrite {
    Param ([string]$logstring)
    $DateStr = Get-Date -Format "MM/dd/yyyy HH:mm:ss"
    Add-Content $Logfile -Value "$DateStr - $logstring"
}

Function Get-LastBusinessDay {
    [CmdletBinding()]
    Param (
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


# Main script execution
LogWrite("Job Start ***********************************************************")
SummaryLogWrite("$jobname Log Starts ------------------------------------------------------------------------------------------------------------------------------")

# Loop after the defined interval to check if file exists

    Try {
		$days=-1
        $runDate = Get-LastBusinessDay -Date (Get-Date).AddDays($days) -DateFormat "yyyy-MM-dd HH:mm:ss"
        $filedatetime = Get-LastBusinessDay -Date (Get-Date).AddDays($days) -DateFormat "MM.dd.yyyy hh.mm"

        $ExecutablePath = "C:\Deployments\InkindMergerProd\InkindMerger\InkindMerger.exe"
        & $ExecutablePath $runDate

        LogWrite("InKind SOD Execution End  --> for run date $runDate")
    }
    Catch {
        $errorMessage = $_.Exception.Message
        LogWrite("Exception Message: $errorMessage")
        SummaryLogWrite("Exception Message: $errorMessage")
    }


LogWrite("Job End ***********************************************************")
SummaryLogWrite("$jobname Log Ends ------------------------------------------------------------------------------------------------------------------------------")
