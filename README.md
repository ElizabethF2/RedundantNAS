# RedundantNAS

RedundantNAS is the precursor to [ReflectiveNAS](https://github.com/ElizabethF2/ReflectiveNAS). Unlike ReflectiveNAS which supports having an infinite number of nodes which asynchronously pull changes from each other, RedundantNAS is designed for only a pair of nodes with each node synchronously pushing changes to the other. This significantly slows down uploads and prevents uploads if one of the nodes is offline which is why RedundantNAS was superseded by ReflectiveNAS. This repo contains the RedundantNAS daemon itself and libnas, a library required to communicate with the daemon as RedundantNAS does not support FUSE like ReflectiveNAS does. Three client applications are also provided:
  - EasiNAS: a GUI file manager
  - NAS-CLI: a CLI file manager
  - AutonomousNAS: a utility for incremental backups
