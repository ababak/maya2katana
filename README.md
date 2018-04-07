# maya2katana

Easily copy shading nodes from [Maya](http://www.autodesk.com/products/maya/overview) to [Katana](https://www.foundry.com/products/katana)

### Currently supported renderers:

- #### [Arnold 4](https://www.solidangle.com/arnold/) with [alShaders](http://www.anderslanglands.com/alshaders/index.html)
  Supported nodes: aiAmbientOcclusion, aiImage, aiNoise, aiStandard, aiUserDataColor,
  aiUserDataFloat, aiVolumeCollector, alCellNoise, alCombineColor, alCombineFloat, alCurvature,
  alFlake, alFlowNoise, alFractal, alHair, alInputScalar, alInputVector, alJitterColor, alLayer,
  alLayerColor, alLayerFloat, alRemapColor, alRemapFloat, alSurface, alSwitchColor, alSwitchFloat,
  alTriplanar, blendColors, bump2d, clamp, luminance, ramp, samplerInfo

- #### [RenderMan 21.7](https://renderman.pixar.com/)
  Supported nodes: not yet (in development)

### Installation

1. Quit Maya

2. Clone maya2katana repository (or download zip, extract and rename directory from "maya2katana-master" to "maya2katana") and place it to:
```
Windows: \Users\<username>\Documents\maya\scripts
Linux: ~/maya/scripts
```

3. Open Script Editor and paste the following code to Python tab:
```
import maya2katana
reload (maya2katana)
maya2katana.copy()
```

4. To create a shelf button select the code and middle-mouse-drag it to your shelf

### Usage

1. Select a shading network or a single shadingEngine (Shading Group) node
![Maya shading network](doc/maya.jpg)

2. Press the button you've created earlier or execute a script (see installation step)

3. Switch to Katana and paste the nodes
![Resulting Katana shading network](doc/katana.jpg)
