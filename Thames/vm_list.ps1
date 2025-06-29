param (
    [string]$Server,
    [string]$User,
    [string]$Password,
    [string]$OutFile = "vms.csv"
)

# Install VMware PowerCLI if not present
if (-not (Get-Module -ListAvailable -Name VMware.PowerCLI)) {
    Write-Host "Installing VMware.PowerCLI..."
    Install-Module -Name VMware.PowerCLI -Scope CurrentUser -Force
    Set-PowerCLIConfiguration -InvalidCertificateAction Ignore -Confirm:$false
}

# Connect to vCenter
Write-Host "Connecting to vCenter $Server ..."
$secPwd = ConvertTo-SecureString $Password -AsPlainText -Force
$cred   = New-Object System.Management.Automation.PSCredential ($User, $secPwd)
Connect-VIServer -Server $Server -Credential $cred | Out-Null

# Get all VMs and export to CSV
Get-VM | Select Name, PowerState, @{N='Cluster';E={$_.VMHost.Parent.Name}} |
    Sort Name |
    Export-Csv -NoTypeInformation -Path $OutFile

Write-Host "VM list written to $OutFile"

Disconnect-VIServer -Server $Server -Confirm:$false
