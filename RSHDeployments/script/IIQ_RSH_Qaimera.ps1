#Log file path
$Logfile = "C:\script\Logs\Log_EXEC_QAIMERA.txt";
$SummaryLogfile = "C:\script\Logs\EXEC_QAIMERASummaryLog.txt";
$jobname = "EXEC_QAIMERA"
$errorMessage = ""

#Function to be used for logging
Function LogWrite
{
	Param ([string]$logstring)
	$DateStr = Get-Date -Format "MM/dd/yyyy HH:mm:ss "
	Add-content $Logfile -value "$DateStr - $logstring"
}

#Function to be used for logging summary
Function SummaryLogWrite
{
	Param ([string]$logstring)
	$DateStr = Get-Date -Format "MM/dd/yyyy HH:mm:ss "
	Add-content $SummaryLogfile -value "$DateStr - $logstring"
}

 function Get-LastBusinessDay {
    [CmdletBinding()]
    param (
        [Parameter(Position = 1)]
        [System.DateTime]$Date = [System.DateTime]::Today,
        [Parameter(Position = 2)]
        [System.String]$DateFormat
    );

    $Weekends = @([System.DayOfWeek]::Saturday, [System.DayOfWeek]::Sunday);
	$LastBusinessDay = $Date.AddDays(-1);

    while ($LastBusinessDay.DayOfWeek -in $Weekends) {
        $LastBusinessDay = $LastBusinessDay.AddDays(-1);
    }

    return $LastBusinessDay.ToString($DateFormat);
}


LogWrite("Job Start ***********************************************************");
SummaryLogWrite("$jobname Log Starts ------------------------------------------------------------------------------------------------------------------------------");




#Loop after the defined interval to check if file exists
	try{
			$days = 0;
			$runDate = Get-LastBusinessDay -Date (Get-Date).AddDays($days) -DateFormat "yyyyMMdd"
			LogWrite("Run Date --> $runDate");
			
			#python C:\Deployments\cosmos\dataloader\qaimera.py $runDate $runDate
             # Change to project root
            Push-Location "C:\Deployments\cosmos"

            # Run script as a module (so util imports work)
            py -3.10 -m dataloader.qaimera $runDate $runDate

            Pop-Location
			
		}
	catch{
			$errorMessage = $($_.Exception.Message);
			LogWrite("Exception Message: $($_.Exception.Message)") 
			SummaryLogWrite("Exception Message: $($_.Exception.Message)");
		}

LogWrite("Job End ***********************************************************");
SummaryLogWrite("$jobname Log Ends ------------------------------------------------------------------------------------------------------------------------------");