Describes changes in each new version of the FDSLoader.

Legend:
  !  Critical Update.
     Affected users should apply this update as soon as possible.
     Necessary for continued operation of the loader. Is time sensitive, or contain important security/connectivity/data integrity updates.
  *  Required Update.  Affected users should plan to apply this update at their next convenience.
     Necessary for continued operation of the loader.
  +  New feature.
     Apply update if needed.
  -  Minor enhancements.
     Apply update if needed.

2.13.7.0 (27-Jan-2025)
 + Added support for Google cloud SQL databases
 + Added support for Amazon Linux 2023
 + Added support for Ubuntu 24.04
 + Added support for Oracle 23
 + Added support for PostgreSQL 16
 + Added support for MariaDB 11
 - Fixed Par global temp excess files issue
 - Updated Documentation and User Guides

2.13.6.0 (19-FEB-2024)
 - Added digital signature on Windows Loader executable file

2.13.6.0 (25-SEPT-2023)
 + Added support for Ubuntu 2022
 + Added support for Red hat 8.x and 9.0
 + Added support for Aurora PostgreSQL 14.x and 15.x
 + Added support for PostgreSQL 15
 - Modified Loader behavior to support Red hat 8.x operating system
 - Updated Linux DSN instructions to support MSSQL ODBC driver 18 for Linux operating systems
 - Modified Loader behavior for bundle command to ignore the spaces between two or more bundle names
 - Updated Documentation and User Guides

2.13.5.0 (31-MAY-2022)
 + Added Windows Server 2022 as a supported operating system
 + Added Ubuntu 2021 as a supported operating system
 + Added support for PostgreSQL 13 and 14
 - Added support to the latest ODBC drivers and altered instructions for DSN setup
 - Modified the Loader behavior to support MySQL ODBC drivers 8.0.24 and above versions
 - Modified the Loader behavior to prevent formation of corrupted files when there is a connection loss
 - Corrected the default version number in the config file

2.13.4.0 (24-DEC-2020)
 + Added CentOS 7 and 8 as a supported operating system
 + Added Amazon Linux 2 as a supported operating system
 - Added support for Windows Server 2019
 - Added support for RHEL 8
 - Added support for Ubuntu 18, 19 and 20
 - Added support for SQL Server 2019
 - Added support for PostgreSQL 11 and 12 
 - [Internal to Factset] Modified Loader behaviour to track the database type for clients

2.13.3.0 (30-APR-2020)
 - Added support for Oracle 19c

2.13.2.0 (19-DEC-2019)
 * Modified Loader behavior to recognize PostgreSQL 11 and PostgreSQL 12 large file processing error 

2.13.1.1 (18-JUL-2019)
 - Modified SQL creation script to grant proper permissions
 - Deprecated support for Windows SQL Server 2008 and 2008 R2 and SQL Server 2008 and 2008R2
 - Updated Linux DSN instructions for correct user and directory use
 - Added recommendations for clients using container-based environments

2.13.1.0 (17-MAY-2019)
  - Modified Loader behavior when running --support command to increase number of logs generated in support file
  - Modified Loader behavior to accommodate custom indexing for PostgreSQL
  * Improved Loader logic to accommodate --force-rebuild command for download-only clients

2.13.0.0 (2-APR-2019)
  - Modified Loader behavior to streamline bulk copying data for Microsoft SQL and Oracle
  
2.12.0.0 (11-MAR-2019)
  - Added ability to change password through command line
  - Added support for special characters in passwords for clients using Oracle

2.11.1.0 (28-FEB-2019)
  - Modified Loader behavior when using Oracle databases
  - Improved Loader behavior if application has not run in over one week

2.11.0.0 (17-JAN-2019)
  - Added support for MySQL 8
  - Added support for Postgres 10
  - Added support for Amazon Aurora (MySQL and Postgres)
  * Modified Loader behavior when on subscriptions that include loading multiple files to the same table
  - Modified Loader behavior during rebuild

2.10.2.0 (9-JAN-2019)
  - Modified Loader behavior when validating and processing zip files

2.10.1.0 (30-AUG-2018)
  - Modified Loader behavior when using Oracle databases on AWS RDS
  - Modified Loader behavior when using proxies

2.10.0.0 (26-JUL-2018)
  - Added support for Oracle 12.2 
  - Added support for Oracle as an AWS RDS endpoint
  - Modified Loader behavior to preserve Oracle format files when utilizing Download Only functionality
  - Modified Loader behavior for Download Only clients 

2.9.0.0 (7-JUN-2018)
  + Added support for Microsoft SQL Server 2017
  + Added support for Microsoft Azure as a supported endpoint
  + Added database compression for Microsoft SQL, Oracle, MySQL, and MariaDB databases
  * Modified Loader behavior when downloading XML transcripts

2.8.1.0 (15-MAR-2018)  
  + Improved Loader behavior when schema sequence increments

2.8.0.0 (22-FEB-2018)
  + Modified required permissions when using Oracle databases
  + Modified Loader behavior to preserve SQL Server format files for use with Microsoft Azure
  + Added purge command to remove unsubscribed bundles from database
  - Modified Loader behavior for long running BCP or PSQL calls

2.7.1.0 (14-DEC-2017)
  + Modified Loader behavior to PostgreSQL databases to handle larger tables
  + Modified Loader behavior to retry corrupted downloads
  + Modified Loader behavior when database connection has failed
  + Modified Microsoft SQL database user creation permissions when using Amazon Relational Database Service

2.7.0.0 (30-NOV-2017)
  + Added support for Microsoft Windows Server 2016, Microsoft Windows 10, Amazon Linux 2017.09, and Red Hat 7
  + Added support for Amazon Web Services Relational Database Service as a supported endpoint
  + Added database specific Table Generation Statements in the \tgs directory for Download Only clients
  + Added database and database user creation scripts for supported databases
  - Modified Loader behavior for when subscribed to XML transcripts
  - Modified Loader behavior when using proxies
  - Modified Loader behavior to provide better error messaging

2.6.0.0 (14-SEP-2017)
  + Added support for MySQL 5.5 through 5.7
  + Added support for MariaDB 5.5 through 10.2
  + Added support for PostgreSQL 9.5 and 9.6
  + Added support for Ubuntu 14.04 and 16.04
  - Modified Loader behavior to delete old schema files
  - Modified Loader behavior to use absolute file paths instead of relative paths
  - Updated support command to create support file which includes log files from last 3 Loader invocations

2.5.4.0 (15-JUN-2017)
  - Modified Loader behavior when utilizing parallelization with Oracle databases

2.5.3.0 (18-MAY-2017)
  - Modified Loader behavior when utilizing Download Only functionality and download path is the same as Loader installation directory

2.5.1.0 (11-MAY-2017)
  - Modified Loader behavior when running support command in Linux
  - Modified Loader behavior for schema files when using Download Only functionality

2.5.0.0 (20-APR-2017)
  + Modified Loader behavior for download only content

2.4.1.0 (23-MAR-2017)
  + Improves behavior when utilizing Windows share folders

2.4.0.0 (2-MAR-2017)
  + Applies version control to config.xml. Please see page 14 of DataFeed Loader User Guide for instructions if upgrading from version 2.2 or 2.3 to 2.4.0.0
  + Parallelization of Loader bundles
  + Obfuscates passwords in config.xml
  + Adds fds.fds_table_locks metadata table
  + Modified logs folder in Loader installation directory and deletes log files older than 30 days
  + Retains table properties after rebuild

2.3.0 (10-OCT-2016)
  + Adds RedHat 6 as supported Operating System
  + Adds SQL Server 2016 as supported database
  * Modified Loader behavior to support zip files over 4gb

2.2.0 (28-JUL-2016)
  + Adds test command
  - Modified proxy support to retrieve information contained in Internet Explorer

2.1.0 (16-MAY-2016)
  + Adds setup command
  + Adds ability to download all subscribed products without bundle command
  + Adds new success value of 2 to indicate Loader is currently running
  + Adds ability to download files without loading into database

2.0.0 (21-MAR-2016)
  +  First release