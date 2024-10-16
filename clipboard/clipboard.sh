HOST=$(hostname -s)
NATS_SERVER="nats://root:r00tpass@ubuntu-dev:4222"
SUBJECT="org.mindwm.${USER}.${HOST}.clipboard"

clipboard_cloudevent() {
    cat<<EOF | jq | nats -s ${NATS_SERVER} pub -H 'ce-specversion: 1.0' -H "ce-id:`uuid`" -H "ce-subject:clipboard" -H "ce-type:org.mindwm.v1.clipboard" -H "ce-source:org.mindwm.${USER}.${HOST}.clipboard" -H "ce-knativebrokerttl:255" -H 'datacontenttype:application/json' ${SUBJECT} 
{
  "uuid": "`uuid`",
  "time": `date +%s`,
  "data": `xclip -o | jq -Rs .`
} 
EOF
}   
while clipnotify; do
  clipboard_cloudevent
done

