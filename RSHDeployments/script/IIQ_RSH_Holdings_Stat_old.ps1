#Log file path
$Logfile = "c:\Logs\Log_ResearchDWH_Holdings_Stat.txt";
$SummaryLogfile = "c:\Logs\EXEC_HoldingsSummaryLog.txt";
$jobname = "ResearchDWH_Holdings_Stat"

#Used for Recursive Script run
$script:counter = 1;
$script:exitcounter = 1;
$timeInterval = 30; # in seconds

#SMTP Details
$smtpUsername = "Alerts_Research@IndexIQ.com";
$smtpPassword = "Connect@2022";
$toEmail ="munawar.gani@ap.linedata.com,nitin.kamble@ap.linedata.com"
#$toEmail ="mkim@indexiq.com,munawar.gani@ap.linedata.com,nitin.kamble@ap.linedata.com,index@indexiq.com"
$errorEmail ="munawar.gani@ap.linedata.com,nitin.kamble@ap.linedata.com"




$successMessage = "Successfully executed the Cosmos Holdings statistic program.";
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
			$message.Subject = "Holdings Data Alert";
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
			
            #$Pricerrex = Invoke-Sqlcmd -ServerInstance "inviiqresearch-sqlserver-standard-dev.ckryme4eosdx.us-east-1.rds.amazonaws.com" -Database "ResearchDWH" -Query "EXEC GetTotallReturnStatData" -QueryTimeout 0 
            
			#Send-ToEmail -email "$toEmail" -emailmessage $Pricerrex[0];
			
			
			$connectionString = "Server=inviiqresearch-sqlserver-standard-dev.ckryme4eosdx.us-east-1.rds.amazonaws.com;Database=ResearchDWH;User Id=stonebranchuser;Password=Welcome@2025;TrustServerCertificate=True;"

			$avgdata = Invoke-Sqlcmd -ConnectionString $connectionString -Query "EXEC sp_getHoldingsForAlert" -QueryTimeout 0

            $avgtable = "<html><style> th {border:2px black solid !important} </style> <style> td {border:2px black solid !important} </style>
             <style> table {border:2px black solid !important} </style><b>ReserchDWH - Holdings Refresh Counts</b></b><br><table>"
            $avgtable += "<tr>"
            $avgtable += "<th>ReferenceId</th>"
            $avgtable += "<th>source</th>"
            $avgtable += "<th>ReferenceCode</th>"
			$avgtable += "<th>Description</th>"
			$avgtable += "<th>Date</th>"
			$avgtable += "<th>Pwgt</th>"
			$avgtable += "<th>N</th>"
            $avgtable += "</tr>"
            
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


          

            $table =$avgtable
			return $table
           
           #write-host $table2
           #Send-ToEmail -email "$toEmail" -emailmessage $table;
           
           
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