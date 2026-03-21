# FreeCAD-Postprocessor-for-Fadal-88HS-controls
This is a FreeCAD CAM Postprocessor for Fadal 88HS controls, it assumes Format 2 is in effect. This is an update to the Fadal post on the pyDNC website, which seemed to have quite a few errors. 

This post is still a work in progress, but had made basic pockets and 2D milling work. Test carefully.

# Known Issues
 - On Linux, python will output LF line endings, but the Fadal seems to choke on them when loading via USB. Use EOL conversion in Notepad++ or similar tools to save the file with Windows style CRLF line endings. 

## Tested Machine
- 1997 Fadal VMC4020 with 88HS control.
- FreeCAD v1.0.2 on Ubuntu

## Validated Operations Checklist

- [x] 2D Adaptive Milling
- [x] Tool Changes
- [x] No Coolant Mode
- [ ] Flood Coolant
- [ ] Mist Coolant
- [ ] 2D Contour
- [ ] 2D Pocket
- [ ] Drilling (G81)
- [X] Peck Drilling (G83)
- [ ] Rigid Tapping (G84)
- [ ] Fixture Offsets
- [ ] Face Milling
- [X] Helix
- [ ] Slot
- [ ] Thread Milling

