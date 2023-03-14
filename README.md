1. MultiCamera 提供了多相机调用。
   OPTCamera 提供了一个相机类，每一个相机对象都是python通过调用dll来单独开一个线程，因此，每个相机的拉流是独立的。
   因此取图可以通过调用 OptCamera.get_image() 获取一帧图像。
   具体原理为dll的相机拉流不断将一帧图片写入某一具体缓存，python读取这一缓存中的内容，并且python读取的这一帧永远是最新的一帧。
   多个相机取图的话，可以顺序调用每个相机(如OPTCamera的main所示)，每两个相机之间的取图时间差为20ms，因此可以近似看为同步取图。

2. 运行例程前，请先安装SDK。

3. SDK的python接口，是将SDK的C接口（头文件详见include目录）转化为对应的Python可以调用的ctypes类型接口。
   转换对应关系如下：
    · SDK.h -> OPTSDK.py
    · ImageConvert.h -> ImageConvert.py   ※图像格式转码模块

4. 该例程适配python2和python3版本
   运行例程前，需安装好python，并在系统环境变量中设置好python相关信息。
   然后，通过执行“python ./Demo.py”运行例程。

5. 例程默认为64位。
   如需使用32位，需要修改加载的SDK库的处理。具体如下：
   · OPTSDK.py        ： Line20注释掉，Line18去注释
   · ImageConvert.py  ： Line15注释掉，Line13去注释

6. python例程中演示了以下功能：
   · 发现相机
   · 打开/关闭相机
   · 开始/停止拉流
   · 设置软/硬触发
   · 单帧采集（采用软触发方式）
   · 保存bmp图片
   · 回调取图和主动取图
   · 设置ROI以及设置曝光

7. 关于SDK的属性读写设置，SDK提供了两种方法

   7.1.SDK提供的属性节点访问
       通过相应的相机对象构造出相应的control节点，通过control节点构造出相应的属性节点，进行读写操作；
       例程中 设置软/硬触发（setSoftTriggerConf/setLineTriggerConf） 即是通过这种方式进行属性读写操作的。

   7.2.通用属性设置（节点）
       根据属性的数据类型（double/int/bool等，可在相机客户端软件的属性窗口查看），通过属性名称，构造出属性节点，从而对属性进行读写操作。
       例程中设置曝光和设置ROI（setExposureTime/setROI） 是通过这种方法进行属性读写操作的。	 

8. 注意

   8.1.python只能运行对应位数的例程。即，32位python运行32位例程，64位python运行64位例程。
   
   8.2.C接口在使用时应注意节点类型和相应的资源不再使用时应及时释放，调用相应的release接口。
       该例程中同样给出了说明；

- END -
