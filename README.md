# maya2katana
Easily copy shading nodes from Maya to Katana

### Currently supported nodes (Arnold with alShaders):
- aiAmbientOcclusion
- aiImage
- aiNoise
- aiUserDataColor
- aiUserDataFloat
- alCellNoise
- alCombineColor
- alCombineFloat
- alCurvature
- alFlake
- alFlowNoise
- alFractal
- alHair
- alInputScalar
- alInputVector
- alJitterColor
- alLayer
- alLayerColor
- alLayerFloat
- alRemapColor
- alRemapFloat
- alSurface
- alSwitchColor
- alSwitchFloat
- alTriplanar
- blendColors
- bump2d
- clamp
- luminance
- ramp
- samplerInfo

### Installation
1. Quit Maya
2. Clone maya2katana repository and place it to:
```
Windows: \Users\<username>\Documents\maya\scripts
Linux: ~/maya/scripts
```
3. Open Script Editor and paste the following code to Python tab:
```
from maya2katana import clip
reload (clip)
clip.copy()
```
4. To create a shelf button select the code and middle-mouse-drag it to your shelf
