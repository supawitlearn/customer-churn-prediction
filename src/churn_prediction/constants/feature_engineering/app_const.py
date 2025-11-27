EVENT_TYPE_MAPPING = {
    'login' : ['mobilews:login','ws:login'],
    'getstationlist' : ['ws:getstationlist','mobilews:getstationlist','adminws:getstationlist','webws:getstationlist'],
    'confirmextension' : ['ws:confirmextension','mobilews:confirmextension'],
    'checkavailablevehiclelist' : ['ws:checkavailablevehiclelist','mobilews:checkavailablevehiclelist','webws:checkavailablevehiclelist'],
    'estimateextension' : ['ws:estimateextension','mobilews:estimateextension'],
    'cancelreservation' : ['ws:cancelreservation','mobilews:cancelreservation'],
    'confirmreservation' : ['ws:confirmreservation','mobilews:confirmreservation','webws:confirmreservation']
}
SESSION_TIMEOUT = 6
ACTIVE_EVENTS = ['confirmextension','mobilews:estimatereservation','checkavailablevehiclelist','confirmreservation','getstationlist','mobilews:getstationvehiclelist','cancelreservation''estimateextension','mobilews:estimateaddonservice','ws:estimatereservation']