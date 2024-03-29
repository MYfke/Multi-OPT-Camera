#!/usr/bin/env python
# coding: utf-8
"""
Created on 2023-03-14

@author: Miao H.Q.
"""

import datetime
import gc
import time

import cv2
import numpy

from ImageConvert import *
from OPTSDK import *


class OptCamera:
    """
    此类提供了两个比较重要的函数，
    get_image(),此函数通过调用可以返回一帧图片
    stop_grabbing(),停止相机对象拉流
    """
    def __init__(self, index, camera):
        self.index = index
        self.camera = camera

        nRet = self.openCamera()
        if nRet != 0:
            print(f"openCamera {index} fail.")

        # 创建流对象
        # create stream source object
        self.streamSourceInfo = GENICAM_StreamSourceInfo()
        self.streamSourceInfo.channelId = index
        self.streamSourceInfo.pCamera = pointer(camera)

        self.streamSource = pointer(GENICAM_StreamSource())
        nRet = GENICAM_createStreamSource(pointer(self.streamSourceInfo), byref(self.streamSource))
        if nRet != 0:
            print("create StreamSource fail!")

        # 通用属性设置:设置触发模式为off --根据属性类型，直接构造属性节点。如触发模式是 enumNode，构造enumNode节点
        # create corresponding property node according to the value type of property, here is enumNode
        # 自由拉流：TriggerMode 需为 off
        # set trigger mode to Off for continuously grabbing
        self.trigModeEnumNode = pointer(GENICAM_EnumNode())
        self.trigModeEnumNodeInfo = GENICAM_EnumNodeInfo()
        self.trigModeEnumNodeInfo.pCamera = pointer(camera)
        self.trigModeEnumNodeInfo.attrName = b"TriggerMode"
        nRet = GENICAM_createEnumNode(byref(self.trigModeEnumNodeInfo), byref(self.trigModeEnumNode))

        if nRet != 0:
            print("create TriggerMode Node fail!")
            # 释放相关资源
            # release node resource before return
            self.streamSource.contents.release(self.streamSource)

        nRet = self.trigModeEnumNode.contents.setValueBySymbol(self.trigModeEnumNode, b"Off")
        if nRet != 0:
            print("set TriggerMode value [Off] fail!")
            # 释放相关资源
            # release node resource before return
            self.trigModeEnumNode.contents.release(self.trigModeEnumNode)
            self.streamSource.contents.release(self.streamSource)

        # 需要释放Node资源
        # release node resource at the end of use
        self.trigModeEnumNode.contents.release(self.trigModeEnumNode)

        # 开始拉流
        # start grabbing
        nRet = self.streamSource.contents.startGrabbing(self.streamSource, c_ulonglong(0),
                                                        c_int(GENICAM_EGrabStrategy.grabStrartegySequential))
        if nRet != 0:
            print("startGrabbing fail!")
            # 释放相关资源
            # release stream source object before return
            self.streamSource.contents.release(self.streamSource)

    def get_image(self):
        # 主动取图
        # get one frame
        frame = pointer(GENICAM_Frame())
        nRet = self.streamSource.contents.getFrame(self.streamSource, byref(frame), c_uint(1000))
        if nRet != 0:
            print("getFrame fail! Timeout:[1000]ms")
            # 释放相关资源
            # release stream source object before return
            self.streamSource.contents.release(self.streamSource)
            return -1
        else:
            print("Camera [" + str(self.index) + "] getFrame success BlockId = [" + str(
                frame.contents.getBlockId(frame)) + "], get frame time: " + str(
                datetime.datetime.now()))

        nRet = frame.contents.valid(frame)
        if nRet != 0:
            print("frame is invalid!")
            # 释放驱动图像缓存资源
            # release frame resource before return
            frame.contents.release(frame)
            # 释放相关资源
            # release stream source object before return
            self.streamSource.contents.release(self.streamSource)
            return -1

            # 给转码所需的参数赋值
        # fill conversion parameter
        imageParams = IMGCNV_SOpenParam()
        imageParams.dataSize = frame.contents.getImageSize(frame)
        imageParams.height = frame.contents.getImageHeight(frame)
        imageParams.width = frame.contents.getImageWidth(frame)
        imageParams.paddingX = frame.contents.getImagePaddingX(frame)
        imageParams.paddingY = frame.contents.getImagePaddingY(frame)
        imageParams.pixelForamt = frame.contents.getImagePixelFormat(frame)

        # 将裸数据图像拷出
        # copy image data out from frame
        imageBuff = frame.contents.getImage(frame)
        userBuff = c_buffer(b'\0', imageParams.dataSize)
        memmove(userBuff, c_char_p(imageBuff), imageParams.dataSize)

        # 释放驱动图像缓存
        # release frame resource at the end of use
        frame.contents.release(frame)

        # 如果图像格式是 Mono8 直接使用
        # no format conversion required for Mono8
        if imageParams.pixelForamt == EPixelType.gvspPixelMono8:
            grayByteArray = bytearray(userBuff)
            cvImage = numpy.array(grayByteArray).reshape(imageParams.height, imageParams.width)
        else:
            # 转码 => BGR24
            # convert to BGR24
            rgbSize = c_int()
            rgbBuff = c_buffer(b'\0', imageParams.height * imageParams.width * 3)

            nRet = IMGCNV_ConvertToBGR24(cast(userBuff, c_void_p),
                                         byref(imageParams),
                                         cast(rgbBuff, c_void_p),
                                         byref(rgbSize))

            colorByteArray = bytearray(rgbBuff)
            cvImage = numpy.array(colorByteArray).reshape(imageParams.height, imageParams.width, 3)
        # --- end if ---
        gc.collect()
        return cvImage

        # --- end while ---

        # cv2.destroyAllWindows()

        # 停止拉流
        # stop grabbing

    def stop_grabbing(self):
        nRet = self.streamSource.contents.stopGrabbing(self.streamSource)
        if nRet != 0:
            print("stopGrabbing fail!")
            # 释放相关资源
            self.streamSource.contents.release(self.streamSource)

        # 关闭相机
        # close camera
        nRet = self.closeCamera()
        if nRet != 0:
            print("closeCamera fail")
            # 释放相关资源
            self.streamSource.contents.release(self.streamSource)

        # 释放相关资源
        # release stream source object at the end of use
        self.streamSource.contents.release(self.streamSource)

    g_cameraStatusUserInfo = b"statusInfo"

    # 相机连接状态回调函数
    # camera connection status change callback
    def deviceLinkNotify(connectArg, linkInfo):
        if EVType.offLine == connectArg.contents.m_event:
            print("camera has off line, userInfo [%s]" % c_char_p(linkInfo).value)
        elif EVType.onLine == connectArg.contents.m_event:
            print("camera has on line, userInfo [%s]" % c_char_p(linkInfo).value)

    connectCallBackFuncEx = connectCallBackEx(deviceLinkNotify)

    # 注册相机连接状态回调
    # subscribe camera connection status change
    def subscribeCameraStatus(self):
        # 注册上下线通知
        # subscribe connection status notify
        eventSubscribe = pointer(GENICAM_EventSubscribe())
        eventSubscribeInfo = GENICAM_EventSubscribeInfo()
        eventSubscribeInfo.pCamera = pointer(self.camera)
        nRet = GENICAM_createEventSubscribe(byref(eventSubscribeInfo), byref(eventSubscribe))
        if nRet != 0:
            print("create eventSubscribe fail!")
            return -1

        nRet = eventSubscribe.contents.subscribeConnectArgsEx(eventSubscribe, self.connectCallBackFuncEx,
                                                              self.g_cameraStatusUserInfo)
        if nRet != 0:
            print("subscribeConnectArgsEx fail!")
            # 释放相关资源
            # release subscribe resource before return
            eventSubscribe.contents.release(eventSubscribe)
            return -1

            # 不再使用时，需释放相关资源
        # release subscribe resource at the end of use
        eventSubscribe.contents.release(eventSubscribe)
        return 0

    # 反注册相机连接状态回调
    # unsubscribe camera connection status change
    def unsubscribeCameraStatus(self):
        # 反注册上下线通知
        # unsubscribe connection status notify
        eventSubscribe = pointer(GENICAM_EventSubscribe())
        eventSubscribeInfo = GENICAM_EventSubscribeInfo()
        eventSubscribeInfo.pCamera = pointer(self.camera)
        nRet = GENICAM_createEventSubscribe(byref(eventSubscribeInfo), byref(eventSubscribe))
        if nRet != 0:
            print("create eventSubscribe fail!")
            return -1

        nRet = eventSubscribe.contents.unsubscribeConnectArgsEx(eventSubscribe, self.connectCallBackFuncEx,
                                                                self.g_cameraStatusUserInfo)
        if nRet != 0:
            print("unsubscribeConnectArgsEx fail!")
            # 释放相关资源
            # release subscribe resource before return
            eventSubscribe.contents.release(eventSubscribe)
            return -1

        # 不再使用时，需释放相关资源
        # release subscribe resource at the end of use
        eventSubscribe.contents.release(eventSubscribe)
        return 0

    # 设置软触发
    # set software trigger
    def setSoftTriggerConf(self):
        # 创建AcquisitionControl节点
        # create AcquisitionControl node
        acqCtrlInfo = GENICAM_AcquisitionControlInfo()
        acqCtrlInfo.pCamera = pointer(self.camera)
        acqCtrl = pointer(GENICAM_AcquisitionControl())
        nRet = GENICAM_createAcquisitionControl(pointer(acqCtrlInfo), byref(acqCtrl))
        if nRet != 0:
            print("create AcquisitionControl fail!")
            return -1

        # 设置触发源为软触发
        # set trigger source to Software
        trigSourceEnumNode = acqCtrl.contents.triggerSource(acqCtrl)
        nRet = trigSourceEnumNode.setValueBySymbol(byref(trigSourceEnumNode), b"Software")
        if nRet != 0:
            print("set TriggerSource value [Software] fail!")
            # 释放相关资源
            # release node resource before return
            trigSourceEnumNode.release(byref(trigSourceEnumNode))
            acqCtrl.contents.release(acqCtrl)
            return -1

        # 需要释放Node资源
        # release node resource at the end of use
        trigSourceEnumNode.release(byref(trigSourceEnumNode))

        # 设置触发方式
        # set trigger selector to FrameStart
        trigSelectorEnumNode = acqCtrl.contents.triggerSelector(acqCtrl)
        nRet = trigSelectorEnumNode.setValueBySymbol(byref(trigSelectorEnumNode), b"FrameStart")
        if nRet != 0:
            print("set TriggerSelector value [FrameStart] fail!")
            # 释放相关资源
            # release node resource before return
            trigSelectorEnumNode.release(byref(trigSelectorEnumNode))
            acqCtrl.contents.release(acqCtrl)
            return -1

        # 需要释放Node资源
        # release node resource at the end of use
        trigSelectorEnumNode.release(byref(trigSelectorEnumNode))

        # 打开触发模式
        # set trigger mode to On
        trigModeEnumNode = acqCtrl.contents.triggerMode(acqCtrl)
        nRet = trigModeEnumNode.setValueBySymbol(byref(trigModeEnumNode), b"On")
        if nRet != 0:
            print("set TriggerMode value [On] fail!")
            # 释放相关资源
            # release node resource before return
            trigModeEnumNode.release(byref(trigModeEnumNode))
            acqCtrl.contents.release(acqCtrl)
            return -1

        # 需要释放相关资源
        # release node resource at the end of use
        trigModeEnumNode.release(byref(trigModeEnumNode))
        acqCtrl.contents.release(acqCtrl)

        return 0

    # 设置外触发
    # set external trigger
    def setLineTriggerConf(self):
        # 创建AcquisitionControl节点
        # create AcquisitionControl node
        acqCtrlInfo = GENICAM_AcquisitionControlInfo()
        acqCtrlInfo.pCamera = pointer(self.camera)
        acqCtrl = pointer(GENICAM_AcquisitionControl())
        nRet = GENICAM_createAcquisitionControl(pointer(acqCtrlInfo), byref(acqCtrl))
        if nRet != 0:
            print("create AcquisitionControl fail!")
            return -1

        # 设置触发源为外触发Line1
        # set trigger source to Line1
        trigSourceEnumNode = acqCtrl.contents.triggerSource(acqCtrl)
        nRet = trigSourceEnumNode.setValueBySymbol(byref(trigSourceEnumNode), b"Line1")
        if nRet != 0:
            print("set TriggerSource value [Line1] fail!")
            # 释放相关资源
            # release node resource before return
            trigSourceEnumNode.release(byref(trigSourceEnumNode))
            acqCtrl.contents.release(acqCtrl)
            return -1

        # 需要释放Node资源
        # release node resource at the end of use
        trigSourceEnumNode.release(byref(trigSourceEnumNode))

        # 设置触发方式
        # set trigger selector to FrameStart
        trigSelectorEnumNode = acqCtrl.contents.triggerSelector(acqCtrl)
        nRet = trigSelectorEnumNode.setValueBySymbol(byref(trigSelectorEnumNode), b"FrameStart")
        if nRet != 0:
            print("set TriggerSelector value [FrameStart] fail!")
            # 释放相关资源
            # release node resource before return
            trigSelectorEnumNode.release(byref(trigSelectorEnumNode))
            acqCtrl.contents.release(acqCtrl)
            return -1

        # 需要释放Node资源
        # release node resource at the end of use
        trigSelectorEnumNode.release(byref(trigSelectorEnumNode))

        # 打开触发模式
        # set trigger mode to On
        trigModeEnumNode = acqCtrl.contents.triggerMode(acqCtrl)
        nRet = trigModeEnumNode.setValueBySymbol(byref(trigModeEnumNode), b"On")
        if nRet != 0:
            print("set TriggerMode value [On] fail!")
            # 释放相关资源
            # release node resource before return
            trigModeEnumNode.release(byref(trigModeEnumNode))
            acqCtrl.contents.release(acqCtrl)
            return -1

        # 需要释放Node资源
        # release node resource at the end of use
        trigModeEnumNode.release(byref(trigModeEnumNode))

        # 设置触发沿
        # set trigger activation to RisingEdge
        trigActivationEnumNode = acqCtrl.contents.triggerActivation(acqCtrl)
        nRet = trigActivationEnumNode.setValueBySymbol(byref(trigActivationEnumNode), b"RisingEdge")
        if nRet != 0:
            print("set TriggerActivation value [RisingEdge] fail!")
            # 释放相关资源
            # release node resource before return
            trigActivationEnumNode.release(byref(trigActivationEnumNode))
            acqCtrl.contents.release(acqCtrl)
            return -1

        # 需要释放Node资源
        # release node resource at the end of use
        trigActivationEnumNode.release(byref(trigActivationEnumNode))
        acqCtrl.contents.release(acqCtrl)
        return 0

    # 打开相机
    # open camera
    def openCamera(self):
        # 连接相机
        # connect camera
        nRet = self.camera.connect(self.camera, c_int(GENICAM_ECameraAccessPermission.accessPermissionControl))
        if nRet != 0:
            print("camera connect fail!")
            return -1
        else:
            print("camera connect success.")

        # 注册相机连接状态回调
        # subscribe camera connection status change
        nRet = self.subscribeCameraStatus()
        if nRet != 0:
            print("subscribeCameraStatus fail!")
            return -1

        return 0

    # 关闭相机
    # close camera
    def closeCamera(self):
        # 反注册相机连接状态回调
        # unsubscribe camera connection status change
        nRet = self.unsubscribeCameraStatus()
        if nRet != 0:
            print("unsubscribeCameraStatus fail!")
            return -1

        # 断开相机
        # disconnect camera
        nRet = self.camera.disConnect(byref(self.camera))
        if nRet != 0:
            print("disConnect camera fail!")
            return -1

        return 0

    # 设置曝光
    # set camera ExposureTime
    def setExposureTime(self, dVal):
        # 通用属性设置:设置曝光 --根据属性类型，直接构造属性节点。如曝光是 double类型，构造doubleNode节点
        # create corresponding property node according to the value type of property, here is doubleNode
        exposureTimeNode = pointer(GENICAM_DoubleNode())
        exposureTimeNodeInfo = GENICAM_DoubleNodeInfo()
        exposureTimeNodeInfo.pCamera = pointer(self.camera)
        exposureTimeNodeInfo.attrName = b"ExposureTime"
        nRet = GENICAM_createDoubleNode(byref(exposureTimeNodeInfo), byref(exposureTimeNode))
        if nRet != 0:
            print("create ExposureTime Node fail!")
            return -1

        # 设置曝光时间
        # set ExposureTime
        nRet = exposureTimeNode.contents.setValue(exposureTimeNode, c_double(dVal))
        if nRet != 0:
            print("set ExposureTime value [%f]us fail!" % dVal)
            # 释放相关资源
            # release node resource before return
            exposureTimeNode.contents.release(exposureTimeNode)
            return -1
        else:
            print("set ExposureTime value [%f]us success." % dVal)

        # 释放节点资源
        # release node resource at the end of use
        exposureTimeNode.contents.release(exposureTimeNode)
        return 0

    def grabOne(self):
        # 创建流对象
        # create stream source object
        streamSourceInfo = GENICAM_StreamSourceInfo()
        streamSourceInfo.channelId = 0
        streamSourceInfo.pCamera = pointer(self.camera)

        streamSource = pointer(GENICAM_StreamSource())
        nRet = GENICAM_createStreamSource(pointer(streamSourceInfo), byref(streamSource))
        if nRet != 0:
            print("create StreamSource fail!")
            return -1

        # 创建AcquisitionControl节点
        # create AcquisitionControl node
        acqCtrlInfo = GENICAM_AcquisitionControlInfo()
        acqCtrlInfo.pCamera = pointer(self.camera)
        acqCtrl = pointer(GENICAM_AcquisitionControl())
        nRet = GENICAM_createAcquisitionControl(pointer(acqCtrlInfo), byref(acqCtrl))
        if nRet != 0:
            print("create AcquisitionControl fail!")
            # 释放相关资源
            # release stream source object before return
            streamSource.contents.release(streamSource)
            return -1

        # 执行一次软触发
        # execute software trigger once
        trigSoftwareCmdNode = acqCtrl.contents.triggerSoftware(acqCtrl)
        nRet = trigSoftwareCmdNode.execute(byref(trigSoftwareCmdNode))
        if nRet != 0:
            print("Execute triggerSoftware fail!")
            # 释放相关资源
            # release node resource before return
            trigSoftwareCmdNode.release(byref(trigSoftwareCmdNode))
            acqCtrl.contents.release(acqCtrl)
            streamSource.contents.release(streamSource)
            return -1

            # 释放相关资源
        # release node resource at the end of use
        trigSoftwareCmdNode.release(byref(trigSoftwareCmdNode))
        acqCtrl.contents.release(acqCtrl)
        streamSource.contents.release(streamSource)

        return 0

    # 设置感兴趣区域  --- 感兴趣区域的宽高 和 xy方向的偏移量  入参值应符合对应相机的递增规则
    # set ROI ---Height, width, offsetX, offsetY. Input value shall comply with the step length and Max & Min limits.
    def setROI(self, OffsetX, OffsetY, nWidth, nHeight):
        # 获取原始的宽度
        # get the max width of image
        widthMaxNode = pointer(GENICAM_IntNode())
        widthMaxNodeInfo = GENICAM_IntNodeInfo()
        widthMaxNodeInfo.pCamera = pointer(self.camera)
        widthMaxNodeInfo.attrName = b"WidthMax"
        nRet = GENICAM_createIntNode(byref(widthMaxNodeInfo), byref(widthMaxNode))
        if nRet != 0:
            print("create WidthMax Node fail!")
            return -1

        oriWidth = c_longlong()
        nRet = widthMaxNode.contents.getValue(widthMaxNode, byref(oriWidth))
        if nRet != 0:
            print("widthMaxNode getValue fail!")
            # 释放相关资源
            # release node resource before return
            widthMaxNode.contents.release(widthMaxNode)
            return -1

            # 释放相关资源
        # release node resource at the end of use
        widthMaxNode.contents.release(widthMaxNode)

        # 获取原始的高度
        # get the max height of image
        heightMaxNode = pointer(GENICAM_IntNode())
        heightMaxNodeInfo = GENICAM_IntNodeInfo()
        heightMaxNodeInfo.pCamera = pointer(self.camera)
        heightMaxNodeInfo.attrName = b"HeightMax"
        nRet = GENICAM_createIntNode(byref(heightMaxNodeInfo), byref(heightMaxNode))
        if nRet != 0:
            print("create HeightMax Node fail!")
            return -1

        oriHeight = c_longlong()
        nRet = heightMaxNode.contents.getValue(heightMaxNode, byref(oriHeight))
        if nRet != 0:
            print("heightMaxNode getValue fail!")
            # 释放相关资源
            # release node resource before return
            heightMaxNode.contents.release(heightMaxNode)
            return -1

        # 释放相关资源
        # release node resource at the end of use
        heightMaxNode.contents.release(heightMaxNode)

        # 检验参数
        # check parameter valid
        if (oriWidth.value < (OffsetX + nWidth)) or (oriHeight.value < (OffsetY + nHeight)):
            print("please check input param!")
            return -1

        # 设置宽度
        # set image width
        widthNode = pointer(GENICAM_IntNode())
        widthNodeInfo = GENICAM_IntNodeInfo()
        widthNodeInfo.pCamera = pointer(self.camera)
        widthNodeInfo.attrName = b"Width"
        nRet = GENICAM_createIntNode(byref(widthNodeInfo), byref(widthNode))
        if nRet != 0:
            print("create Width Node fail!")
            return -1

        nRet = widthNode.contents.setValue(widthNode, c_longlong(nWidth))
        if nRet != 0:
            print("widthNode setValue [%d] fail!" % nWidth)
            # 释放相关资源
            # release node resource before return
            widthNode.contents.release(widthNode)
            return -1

            # 释放相关资源
        # release node resource at the end of use
        widthNode.contents.release(widthNode)

        # 设置高度
        # set image height
        heightNode = pointer(GENICAM_IntNode())
        heightNodeInfo = GENICAM_IntNodeInfo()
        heightNodeInfo.pCamera = pointer(self.camera)
        heightNodeInfo.attrName = b"Height"
        nRet = GENICAM_createIntNode(byref(heightNodeInfo), byref(heightNode))
        if nRet != 0:
            print("create Height Node fail!")
            return -1

        nRet = heightNode.contents.setValue(heightNode, c_longlong(nHeight))
        if nRet != 0:
            print("heightNode setValue [%d] fail!" % nHeight)
            # 释放相关资源
            # release node resource before return
            heightNode.contents.release(heightNode)
            return -1

            # 释放相关资源
        # release node resource at the end of use
        heightNode.contents.release(heightNode)

        # 设置OffsetX
        # set OffsetX
        OffsetXNode = pointer(GENICAM_IntNode())
        OffsetXNodeInfo = GENICAM_IntNodeInfo()
        OffsetXNodeInfo.pCamera = pointer(self.camera)
        OffsetXNodeInfo.attrName = b"OffsetX"
        nRet = GENICAM_createIntNode(byref(OffsetXNodeInfo), byref(OffsetXNode))
        if nRet != 0:
            print("create OffsetX Node fail!")
            return -1

        nRet = OffsetXNode.contents.setValue(OffsetXNode, c_longlong(OffsetX))
        if nRet != 0:
            print("OffsetX setValue [%d] fail!" % OffsetX)
            # 释放相关资源
            # release node resource before return
            OffsetXNode.contents.release(OffsetXNode)
            return -1

            # 释放相关资源
        # release node resource at the end of use
        OffsetXNode.contents.release(OffsetXNode)

        # 设置OffsetY
        # set OffsetY
        OffsetYNode = pointer(GENICAM_IntNode())
        OffsetYNodeInfo = GENICAM_IntNodeInfo()
        OffsetYNodeInfo.pCamera = pointer(self.camera)
        OffsetYNodeInfo.attrName = b"OffsetY"
        nRet = GENICAM_createIntNode(byref(OffsetYNodeInfo), byref(OffsetYNode))
        if nRet != 0:
            print("create OffsetY Node fail!")
            return -1

        nRet = OffsetYNode.contents.setValue(OffsetYNode, c_longlong(OffsetY))
        if nRet != 0:
            print("OffsetY setValue [%d] fail!" % OffsetY)
            # 释放相关资源
            # release node resource before return
            OffsetYNode.contents.release(OffsetYNode)
            return -1

            # 释放相关资源
        # release node resource at the end of use
        OffsetYNode.contents.release(OffsetYNode)
        return 0


# 枚举相机
# enumerate camera
def enumCameras():
    # 获取系统单例
    # get system instance
    system = pointer(GENICAM_System())
    nRet = GENICAM_getSystemInstance(byref(system))
    if nRet != 0:
        print("getSystemInstance fail!")
        return None, None

    # 发现相机
    # discover camera
    cameraList = pointer(GENICAM_Camera())
    cameraCnt = c_uint()
    nRet = system.contents.discovery(system, byref(cameraList), byref(cameraCnt),
                                     c_int(GENICAM_EProtocolType.typeAll))
    if nRet != 0:
        print("discovery fail!")
        return None, None
    elif cameraCnt.value < 1:
        print("discovery no camera!")
        return None, None
    else:
        print("cameraCnt: " + str(cameraCnt.value))
        return cameraCnt.value, cameraList


if __name__ == '__main__':

    streamSourceList = []
    cameraCnt, cameras_info = enumCameras()
    if cameraCnt is None:
        print("Can't find camera")

    # 显示相机信息
    # print camera info
    threads = []
    camera_list = []
    for index in range(0, cameraCnt):
        camera_info = cameras_info[index]
        print("\nCamera Id = " + str(index))
        print("Key           = " + str(camera_info.getKey(camera_info)))
        print("vendor name   = " + str(camera_info.getVendorName(camera_info)))
        print("Model  name   = " + str(camera_info.getModelName(camera_info)))
        print("Serial number = " + str(camera_info.getSerialNumber(camera_info)))
        print("-------------------------------")
        camera = OptCamera(index, camera_info)
        camera_list.append(camera)

    while True:
        cvImage = camera_list[0].get_image()
        cv2.imshow(f'myWindow0', cvImage)
        cvImage = camera_list[1].get_image()
        cv2.imshow(f'myWindow1', cvImage)
        gc.collect()

        if cv2.waitKey(1) >= 0:
            # isGrab = False
            break
    print("--------- Demo end ---------")
    # 3s exit
    time.sleep(0.5)
