<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28.0" styleCategories="AllStyleCategories">
  <pipe>
    <rasterrenderer type="singlebandpseudocolor" band="1" opacity="1" alphaBand="-1" classificationMin="-50" classificationMax="50">
      <rastershader>
        <colorrampshader colorRampType="INTERPOLATED" clip="0" classificationMode="1">
          <item value="-40" color="#b13e82" alpha="255" label="&lt;= -40"/>
          <item value="-30" color="#d45f34" alpha="255" label="-40 - -30"/>
          <item value="-20" color="#f2c73d" alpha="255" label="-30 - -20"/>
          <item value="-10" color="#dcf570" alpha="255" label="-20 - -10"/>
          <item value="0"   color="#c0f5d5" alpha="255" label="-10 - 10"/>
          <item value="10"  color="#c0f5d5" alpha="255" label="-10 - 10"/>
          <item value="20"  color="#7be8d1" alpha="255" label="10 - 20"/>
          <item value="30"  color="#4baef8" alpha="255" label="20 - 30"/>
          <item value="40"  color="#0027f6" alpha="255" label="30 - 40"/>
          <item value="50"  color="#05007a" alpha="255" label="&gt; 40"/>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
  </pipe>
</qgis>
