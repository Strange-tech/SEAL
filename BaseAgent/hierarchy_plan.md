# A hierarchical structure of LayoutAgents and ArtiAgents

BaseAgent 需要是一个一直运行的进程，用户输入一句话，他要给回复，完毕之后等待用户输入下一句指令。BaseAgent有两个subagent：LayoutAgent和ArtiAgent（在johnli目录下），这两个subagent有各自独立的system prompt，sdk，session等（即这两个项目内的所有文件是独立持有的），同时，这两个subagent的session记录会被压缩后共享在BaseAgent的session中

用户给--image input/xx.png --task "reconstruct xxx"，BaseAgent一定会首先调用LayoutAgent，得到layout（room.py），然后对layout中的每个box并行地调用ArtiAgent。注意：现在的Artigent仅支持图像（sam3得到的对应mask）和text（VLM看图给描述）作为输入，并没有支持box的约束。但这个功能是要添加的，可以是--box xxx，然后物体就会被约束在这个box的scale和position中生成，同时根据VLM推理，给一个物体正面方向作为z轴朝向，物体上方作为y轴（这应该是和LayoutAgent一致的）

最重要的设计：
1. Dual-Agent hierarchical Framework: LayoutAgent和ArtiAgent分层解耦，分别负责场景的结构和物体精细几何
2. Bidirectional Iterative Optimization Loop: 资产反馈布局，让布局能够自适应铰链物体的形变（真实包围盒），消除碰撞与悬空
3. Cross-Object Mutual Adaptation: 解决多个物体几何相互干扰问题，比如添加窗户会影响墙壁，墙壁需要被挖空

实现途径：
1. ArtiAgent实现一个tool（真实包围盒），他返回铰链物体所有关节的活动范围所占据的包围盒，LayoutAgent拿到这个包围盒之后，再重新compile布局
2. 新增的嵌入关系会影响两个物体本身的几何，比如墙壁被窗户嵌入，那么墙壁需要调用cad sdk（差集）挖去这一部分