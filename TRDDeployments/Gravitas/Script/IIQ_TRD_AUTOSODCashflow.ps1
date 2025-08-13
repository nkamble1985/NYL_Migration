#Log file path
$Logfile = "C:\Gravitas\Logs\Execute_AUTO_SODLog.txt";
$SummaryLogfile = "C:\Gravitas\Logs\EquitizerSummaryLog.txt";
$jobname = "Execute_AUTO_SOD"

#Used for Recursive Script run
#SMTP Details
$errorMessage = "";

#Function to be used for logging summary
Function SummaryLogWrite
{
	Param ([string]$logstring)
	$DateStr = Get-Date -Format "MM/dd/yyyy HH:mm:ss "
	Add-content $SummaryLogfile -value "$DateStr - $logstring"
}
#Function to be used for logging
Function LogWrite
{
	Param ([string]$logstring)
	$DateStr = Get-Date -Format "MM/dd/yyyy HH:mm:ss"
	Add-content $Logfile -value "$DateStr - $logstring"
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
	$LastBusinessDay = $Date.AddDays(0);

    while ($LastBusinessDay.DayOfWeek -in $Weekends) {
        $LastBusinessDay = $LastBusinessDay.AddDays(0);
    }

    return $LastBusinessDay.ToString($DateFormat);
}

 
LogWrite("Job Start ***********************************************************");
SummaryLogWrite("$jobname Log Starts ------------------------------------------------------------------------------------------------------------------------------");
#Loop after the defined interval to check if file exists



	
		try{
				
				$days = -1;
				$runDate = Get-LastBusinessDay -Date (Get-Date).AddDays($days) -DateFormat "yyyy-MM-dd HH:mm:ss"
				$filedatetime = Get-LastBusinessDay -Date (Get-Date).AddDays($days) -DateFormat "MM.dd.yyyy hh.mm"

				$ExecutablePath = "C:\Deployments\AUTOSOD\AUTOSODCashflow.exe"
		        & $ExecutablePath $runDate
				
			}
		catch{
					$errorMessage = $($_.Exception.Message);
					LogWrite("Exception Message: $($_.Exception.Message)");
					SummaryLogWrite("Exception Message: $($_.Exception.Message)");
			}
			
LogWrite("Job End ***********************************************************");
SummaryLogWrite("$jobname Log Ends ------------------------------------------------------------------------------------------------------------------------------");
 
 
