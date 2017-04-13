# maya2katana
Easily copy shading nodes from Maya to Katana

Currently supported nodes (Arnold with alShaders):
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

Installation
We only need a couple of lines of code to run a Python file from Maya but before we attempt this we need to make sure the Python file(s) are in the correct location: a valid Maya Python path. There are ways to set custom Maya Python paths but most users opt for the default paths which are different depending on your OS:

Windows: <drive>:\Documents and Settings\<username>\My Documents\maya\<Version>\scripts
Linux: ~/maya/<version>/scripts
