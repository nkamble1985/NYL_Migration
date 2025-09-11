#Log file path
$Logfile = "D:\SchedulerLogs\MSFileUnzipLog.txt";
$filepath = "C:\Gravitas\VendorFiles\MSTAN\DailyMargin\"
$fileNamePattern = "_MS_INDEXIQ_PR_*.zip"; #20230809_MS_INDEXIQ_PR_*.zip
$fileName = "";

#Function to be used for logging
Function LogWrite
{
	Param ([string]$logstring)
	$DateStr = Get-Date -Format "MM/dd/yyyy HH:mm:ss "
	Add-content $Logfile -value "$DateStr - $logstring"
}

#Function to be used for fetching last business date
function Get-LastBusinessDay {
    [CmdletBinding()]
    param (
        [Parameter(Position = 1)]
        [System.DateTime]$Date = [System.DateTime]::Today
    );

    $Weekends = @([System.DayOfWeek]::Saturday, [System.DayOfWeek]::Sunday);
	$LastBusinessDay = $Date.AddDays(-1);

    while (($LastBusinessDay.DayOfWeek -in $Weekends)) {
        $LastBusinessDay = $LastBusinessDay.AddDays(-1);
    }

    return $LastBusinessDay.ToString("yyyyMMdd");
}


LogWrite("Job Started.")
try
	{
		#20230809_MS_INDEXIQ_PR_*.zip
		$datePattern = Get-LastBusinessDay -Date (Get-Date).AddDays(0).ToString("yyyy-MM-dd");
		$fileName = $datePattern + $fileNamePattern;
		LogWrite("fileName: $fileName");
		
		$zipfile = Get-ChildItem -Path $filepath -Filter *.zip | Where-Object {$_.Name -like $fileName} | Select-Object -ExpandProperty Name
		LogWrite("zipfile: $zipfile");
		
		$fullpath = $filepath + $zipfile;
		#LogWrite("fullpath: $fullpath");
		
		if ($zipfile) 
		{
				Expand-Archive -LiteralPath $fullpath -DestinationPath $filepath -Force;
				LogWrite("Extracted $zipfile");
				
		}
		else
		{
			LogWrite("ZIP File Not Found : $fileName");
		}
	}
	catch
	{
		
		LogWrite("Main - Exception Message: $($_.Exception.Message)");
		
		
	}
LogWrite("Job Completed.")