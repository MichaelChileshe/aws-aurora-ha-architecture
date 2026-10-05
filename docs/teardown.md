# Teardown

Aurora bills by the hour, so teardown happened the same morning as the build. Nothing has deletion protection and there's no `Deny` statement anywhere, so every delete works for the account administrator. Order matters only where AWS enforces it: instances before their cluster, a clone before its source, the database security group before the one it references.

Run from the repo folder after `source ./env.sh`.

## A: start every deletion at once

```bash
aws application-autoscaling deregister-scalable-target --service-namespace rds --resource-id cluster:themba-claims --scalable-dimension rds:cluster:ReadReplicaCount
aws rds delete-db-cluster-endpoint --db-cluster-endpoint-identifier themba-reporting --query Status --output text
aws rds delete-db-instance --db-instance-identifier themba-claims-test-1 --query DBInstance.DBInstanceStatus --output text
for i in $(aws rds describe-db-clusters --db-cluster-identifier themba-claims --query 'DBClusters[0].DBClusterMembers[].DBInstanceIdentifier' --output text); do aws rds delete-db-instance --db-instance-identifier "$i" --query DBInstance.DBInstanceStatus --output text; done
aws ec2 terminate-instances --instance-ids "$LOADBOX_ID" --query 'TerminatingInstances[0].CurrentState.Name' --output text
```

Deregistering the scalable target removes its scaling policy and alarms. The loop deletes **every** member of the cluster, including any replica that auto scaling might have added, rather than a hard-coded list.

## B: wait for the instances to go

```bash
until [ "$(aws rds describe-db-clusters --db-cluster-identifier themba-claims --query 'length(DBClusters[0].DBClusterMembers)' --output text)" = "0" ]; do sleep 30; done
until [ "$(aws rds describe-db-clusters --db-cluster-identifier themba-claims-test --query 'length(DBClusters[0].DBClusterMembers)' --output text)" = "0" ]; do sleep 30; done
aws ec2 wait instance-terminated --instance-ids "$LOADBOX_ID"
```

## C: clusters (clone first), then the subnet group

```bash
aws rds delete-db-cluster --db-cluster-identifier themba-claims-test --skip-final-snapshot --delete-automated-backups --query DBCluster.Status --output text
aws rds delete-db-cluster --db-cluster-identifier themba-claims --skip-final-snapshot --delete-automated-backups --query DBCluster.Status --output text
aws rds wait db-cluster-deleted --db-cluster-identifier themba-claims-test
aws rds wait db-cluster-deleted --db-cluster-identifier themba-claims
aws rds delete-db-subnet-group --db-subnet-group-name themba-claims-db
```

`--skip-final-snapshot --delete-automated-backups` leaves nothing behind that bills for storage. In production I'd keep a final snapshot. Deleting the cluster also deletes its RDS-managed master secret.

## D: IAM and network

```bash
aws iam remove-role-from-instance-profile --instance-profile-name themba-loadbox-profile --role-name themba-loadbox-role
aws iam delete-instance-profile --instance-profile-name themba-loadbox-profile
aws iam detach-role-policy --role-name themba-loadbox-role --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam delete-role-policy --role-name themba-loadbox-role --policy-name claims-loadbox
aws iam delete-role --role-name themba-loadbox-role
aws ec2 delete-security-group --group-id "$DB_SG"
aws ec2 delete-security-group --group-id "$LOADBOX_SG"
aws ec2 delete-subnet --subnet-id "$PUB_SUBNET"
aws ec2 delete-subnet --subnet-id "$PRIV_A"
aws ec2 delete-subnet --subnet-id "$PRIV_B"
aws ec2 delete-route-table --route-table-id "$PUB_RT"
aws ec2 detach-internet-gateway --internet-gateway-id "$IGW_ID" --vpc-id "$VPC_ID"
aws ec2 delete-internet-gateway --internet-gateway-id "$IGW_ID"
aws ec2 delete-vpc --vpc-id "$VPC_ID"
```

The DB security group goes first because its rule references the load box's group. A `DependencyViolation` on a group or subnet means a network interface is still being released; it clears within a minute.

## Clean check

```bash
aws rds describe-db-clusters --query "DBClusters[?starts_with(DBClusterIdentifier,'themba')].DBClusterIdentifier" --output text
aws rds describe-db-instances --query "DBInstances[?starts_with(DBInstanceIdentifier,'themba')].DBInstanceIdentifier" --output text
aws rds describe-db-cluster-snapshots --snapshot-type manual --query "DBClusterSnapshots[?starts_with(DBClusterIdentifier,'themba')].DBClusterSnapshotIdentifier" --output text
aws secretsmanager list-secrets --query 'SecretList[?starts_with(Name,`rds!cluster`)].Name' --output text
aws ec2 describe-instances --filters Name=tag:Name,Values=themba-loadbox Name=instance-state-name,Values=running,stopped --query 'Reservations[].Instances[].InstanceId' --output text
aws ec2 describe-vpcs --filters Name=tag:Name,Values=themba-aurora-vpc --query 'Vpcs[].VpcId' --output text
aws iam list-roles --query "Roles[?starts_with(RoleName,'themba-loadbox')].RoleName" --output text
```

The secrets query uses **single** quotes on purpose: in double quotes, bash reads `!cluster` as history expansion and the line never runs (note 3 in [`debugging-journey.md`](debugging-journey.md)).

My first run printed only `event not found`: bash had rejected the whole block, so nothing was checked ([`25`](screenshots/25-step13-clean-check.png)). The re-run with the corrected quoting came back empty on every line ([`26`](screenshots/26-step13-clean-check-rerun.png)). A managed secret can show for a short while after its cluster is deleted, while it's scheduled for deletion, and then disappears on its own.

The Application Auto Scaling service-linked role (`AWSServiceRoleForApplicationAutoScaling_RDSCluster`) stays. It's shared, costs nothing and is reused next time.
