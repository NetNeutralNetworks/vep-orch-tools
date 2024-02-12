#!/bin/sh -f

PLACE=".1.3.6.1.4.1.61192.0.1"   # ncubed edge platform
REQ="$2"                         # Requested OID

# .0.x opbjectid's , not used
# .1.x general
# .2.<ojectid>.y object specific 

#
#  GETNEXT requests - determine next valid instance
#
if [ "$1" = "-n" ]; then
  case "$REQ" in
    $PLACE|             \
    $PLACE.0|           \
    $PLACE.0.*|         \
    $PLACE.1)      RET=$PLACE.1.0 ;;     # netSnmpPassString.0
    $PLACE.1.0)    RET=$PLACE.1.1 ;;
    $PLACE.1.1)    RET=$PLACE.1.2 ;;
    $PLACE.1.2)    RET=$PLACE.1.3 ;;
    $PLACE.1.3)    RET=$PLACE.1.4 ;;
    $PLACE.1.4)    RET=$PLACE.1.5 ;;
    $PLACE.1.5)    RET=$PLACE.1.6 ;;
    $PLACE.1.6)    RET=$PLACE.1.7 ;;
    *)              exit 0 ;;
  esac
else

#
#  GET requests - check for valid instance
#
  case "$REQ" in
    $PLACE.1.0|         \
    $PLACE.1.1|         \
    $PLACE.1.2|         \
    $PLACE.1.3|         \
    $PLACE.1.4|         \
    $PLACE.1.5|         \
    $PLACE.1.6|         \
    $PLACE.1.7)     RET=$REQ ;;
    *)              exit 0 ;;
  esac
fi

#
#  "Process" GET* requests - return value
#
echo "$RET"
case "$RET" in
  $PLACE.1.0)     echo "string";    n3 show platform | sed s/.*:.//g;   exit 0 ;;
  $PLACE.1.1)     echo "string";    n3 show serial | sed s/.*:.//g;     exit 0 ;;
  $PLACE.1.2)     echo "string";    n3 show version | sed s/.*:.//g;    exit 0 ;;
  $PLACE.1.3)     echo "string";    grep DISTRIB_DESCRIPTION /etc/lsb-release | cut -d '"' -f2; exit 0 ;;
  $PLACE.1.4)     echo "integer";    cat /var/lib/update-notifier/updates-available | grep sec | cut -d ' ' -f1; exit 0 ;;
  $PLACE.1.5)     echo "integer";    cat /var/lib/update-notifier/updates-available | grep 'updates can be applied immediately' | cut -d ' ' -f1; exit 0 ;;
  $PLACE.1.6)     echo "string";    if test -f /var/run/reboot-required; then cat /var/run/reboot-required; fi; exit 0 ;;
  $PLACE.1.7)     echo "integer";    if test -f /opt/ncubed/config/local/system.yaml; then grep "member:" /opt/ncubed/config/local/system.yaml | sed s/.*:.//g; fi; exit 0 ;;
  *)              echo "string";    echo "ack... $RET $REQ"; exit 0 ;;  # Should not happen
esac




