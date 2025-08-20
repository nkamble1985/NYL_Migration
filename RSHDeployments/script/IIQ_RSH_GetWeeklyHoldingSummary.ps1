#Log file path
$Logfile = "c:\Logs\Log_EXEC_WeeklyHoldingSummary.txt";
$SummaryLogfile = "c:\Logs\EXEC_WeeklyHoldingSummaryLog.txt";
$jobname = "EXEC_Holdings"

#Used for Recursive Script run
$script:counter = 1;
$script:exitcounter = 1;
$timeInterval = 30; # in seconds

#SMTP Details
$smtpUsername = "Alerts_Research@IndexIQ.com";
$smtpPassword = "Connect@2022";
$toEmail = "munawar.gani@ap.linedata.com,nitin.kamble@ap.linedata.com,alerts@gravitas.co";#"mkim@indexiq.com,munawar.gani@ap.linedata.com,nitin.kamble@ap.linedata.com,index@indexiq.com,alerts@gravitas.co"
$errorEmail = "munawar.gani@ap.linedata.com,nitin.kamble@ap.linedata.com,alerts@gravitas.co";#




$successMessage = "Successfully executed the Cosmos Weekly Holding Summary statistic program.";
$errorMessage = "";

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

#Function to be used for sending email
function Send-ToEmail([string]$email, [string]$emailmessage)
{
	try{
			$message = new-object Net.Mail.MailMessage;
			$message.From = $smtpUsername;
			$message.To.Add($email);
			$message.Subject = "Weekly Holding Data Summary";
            $message.IsBodyHTML = $true
			$message.Body = $emailmessage;
			
			$smtp = new-object Net.Mail.SmtpClient("smtp.office365.com", "587");
			$smtp.EnableSSL = $true;
            
			$smtp.Credentials = New-Object System.Net.NetworkCredential($smtpUsername, $smtpPassword);
			#$smtp.send($message);
		}
	catch{
			$errorMessage = $($_.Exception.Message);
			LogWrite("Send-ToEmail - Exception Message: $($_.Exception.Message)")
		}
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
while($script:counter -le $script:exitcounter) {
	LogWrite("Starting counter - $script:counter");
	try{
			$days = 0;
			$runDate = Get-LastBusinessDay -Date (Get-Date).AddDays($days) -DateFormat "yyyyMMdd"
			LogWrite("Run Date --> $runDate");
			
			
			
			
           
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


            return $returntable


            

           
           #write-host $table2
		   #LogWrite("Data: $table2");
           #Send-ToEmail -email "$toEmail" -emailmessage $returntable;
           
           
		}
	catch{
			$errorMessage = $($_.Exception.Message);
			LogWrite("Exception Message: $($_.Exception.Message)");
			SummaryLogWrite("Exception Message: $($_.Exception.Message)");
			#Send-ToEmail -email "$errorEmail" -emailmessage "$errorMessage";
		}
	Start-Sleep -Seconds $timeInterval
	LogWrite("Ending counter - $script:counter");
	$script:counter += 1
}
LogWrite("Job End ***********************************************************");
SummaryLogWrite("$jobname Log Ends ------------------------------------------------------------------------------------------------------------------------------");