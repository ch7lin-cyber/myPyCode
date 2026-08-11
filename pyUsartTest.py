'''USART Config = 115200,8,N,1,RTU   , modbus protocal
''' Config站號1,2,3共三台,每台有四個通道
''' address PV =1000~1003h,
''' address SensorType = 1100~1103h,0:TC_k,14:PT100
''' address CJC_source = 1120~1123h,0:Internal,1:External,2:HostPV4
''' address braodCast hostPV4 = 4718h
'''
'''於下面產生測試 python測試code
'''測試1:讀三台PV是否可讀無錯誤碼，並寫讀CJC_source:0/1/2/3,寫入3會fail
'''測試2:對站號1測試:

##############以上是測試計劃 ##########################

##############以下是python code########################

