DemandFS
========

What is DemandFS?
-----------------

DemandFS is a filesystem-layer for unix-like systems using FUSE.  
Like autofs and autmount it shall execute a mount if a specific direcotry 
receives a filesystem request and do also a unmount after the filesystem was 
idle for some time. Additional it has following features:

* the first request on the filesystem will block until the mount-script in 
the background has finished.
* it can execute a script (to unmout) after the idle-timeout for the filesystem 
has reached

How does it work?
-----------------

DemandFS is *not* a daemon - it uses FUSE to be mounted on a specific directory. 
Its main part is a layer between the **mountpoint** where it was mounted 
and the **backdir**, which has the data. Every call for the mountpoint will 
be mapped to the backdir.  
If the backdir is not mounted, the request will fire a trigger which 
starts a script specified as **mountscript**. If this scripts return with 0 
as returncode, the request will be mapped to backdir.  
After the filesystem is idle for some seconds, specified as **timeout**,  
DemandFS will call the **unmountscript** to unmount the backdir.

Mountoptions
------------

* **backdir**: The directory where the mountscritp mounts the directory. This 
directory really holds the data. DemandFS will work as a mapper between its 
own mountpoint and this directory.
* **mountscript**: Path to the script which is called to mount the backdir.
* **umountscript**: Path the script which unmounts the backdir
* **timeout**: Time in secods after last avitivty, DemandFS will try to call 
the unmountscript whe the timeout is reached.  
DemandFS checks the idle-steate of the FS only every 30 seconds, so it can 
take this time longer before the unmount is called. 

Other Options
-------------

* **-f*: will run DemandFS in the foreground (might be easier to find problems)

Example
-------

``` bash
    tmp # cat mount.sh
    #!/bin/bash
    mount -t nfs -o rw 192.168.1.3:/Daten /mnt/back_server
    exit $?

    tmp # cat unmount.sh
    #!/bin/bash
    umount /mnt/back_server
    exit $?

    tmp # demandfs.py -o backdir=/mnt/back_server,mountscript=/tmp/mount.sh,umountscript=/tmp/unmount.sh,timeout=60 /mnt/server
```

The both scripts in /tmp will do the mount and unmount of the source, a NFS 
share in this case. They will mount it to /mnt/server_back.  
DemandFS mountpoint is /mnt/server. If any request will reach this 
destination, it will call the mountscript and (if it does not fail) the data 
will be available in /mnt/server.  
If /mnt/server is idle for 60 seconds, DemandFS will call the script to 
unmount.
 