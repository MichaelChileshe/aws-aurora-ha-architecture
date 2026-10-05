{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DiscoverClustersAndEndpoints",
      "Effect": "Allow",
      "Action": ["rds:DescribeDBClusters", "rds:DescribeDBClusterEndpoints", "rds:DescribeDBInstances"],
      "Resource": "*"
    },
    {
      "Sid": "FailoverTheClaimsClusterOnly",
      "Effect": "Allow",
      "Action": "rds:FailoverDBCluster",
      "Resource": [
        "arn:aws:rds:@@REGION@@:@@ACCOUNT_ID@@:cluster:themba-claims",
        "arn:aws:rds:@@REGION@@:@@ACCOUNT_ID@@:db:themba-claims-*"
      ]
    },
    {
      "Sid": "ReadRdsManagedMasterSecretsOnly",
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:@@REGION@@:@@ACCOUNT_ID@@:secret:rds!cluster-*"
    }
  ]
}
