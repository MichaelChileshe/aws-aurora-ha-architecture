# ADR 0006: No passwords typed, no inbound access

**Status:** Accepted
**Context:** The database holds policyholder data. The load box needs to reach it, and I need to reach the load box.

## Decision

| Concern | Control |
|---|---|
| Database password | `--manage-master-user-password`: RDS generates it and keeps it in Secrets Manager (`rds!cluster-…`). The tool reads it at run time through the instance role |
| Who can read it | The load box role may call `GetSecretValue` on `secret:rds!cluster-*` only |
| Network path to the database | Private subnets with no internet route. The DB security group allows 5432 **from the load box's security group** only (a group reference, not an IP range) |
| Network path to the load box | No inbound rules, no key pair. Shell access through **Session Manager** (`AmazonSSMManagedInstanceCore`) |
| Instance metadata | IMDSv2 required (`HttpTokens=required`) |
| Encryption | Encrypted cluster volume; every connection uses `sslmode=require` |
| Failover permission | `rds:FailoverDBCluster` on `themba-claims` and its instances only |

## Consequences

- The password never appeared on screen, in a file, in `env.sh` or in shell history.
- The load box's outbound internet access exists only to install packages and call AWS APIs. In production, VPC endpoints would remove that need (see `aws-private-connectivity-endpoints`).
- The managed secret can be rotated by RDS without changing anything in the tool.
- Deleting the cluster deletes its managed secret: nothing to clean up separately.
