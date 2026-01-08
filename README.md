# BlenderJPS - JuPedSim Trajectory Importer for Blender

A Blender addon for importing JuPedSim simulation SQLite files, visualizing agent trajectories and simulation geometry.

![Addon Preview](images/preview.png)

## Features

- **Import JuPedSim SQLite files**: Load trajectory data and walkable area geometry
- **Animated Agents**: Each agent is represented as an animated sphere following their trajectory
- **Geometry Visualization**: Walkable area boundaries and obstacles are displayed as curves
- **Easy Installation**: Built-in dependency installer for required Python packages

## Requirements

- **Blender 4.0+** (tested with Blender 4.0 and later)
- **Python packages**: `pedpy`, `numpy<2.0` (installed automatically via addon)

> **Note:** While `pedpy` currently only used to open sqlite files, something that pandas can also do natively, we include it for maintainability and to prepare for future features that will leverage its visualization and processing capabilities.

## Installation

### Step 1: Download the Addon

Download or clone this repository. You need the `blender_jps` folder.

### Step 2: Install in Blender

#### Option A: Install from ZIP
1. Zip the `blender_jps` folder (the folder itself, not its contents)
2. Open Blender
3. Go to **Edit → Preferences → Add-ons**
4. Click **Install...** and select the ZIP file
5. Enable the addon by checking the box next to "BlenderJPS - JuPedSim Importer"

#### Option B: Manual Installation (Symbolic Link)
Create a symbolic link to your `blender_jps` folder in your Blender addons directory. This allows for easier development as changes are reflected immediately.

**Windows:**
1. Open Command Prompt or PowerShell as Administrator
2. Navigate to your Blender addons directory:
   ```cmd
   cd "%APPDATA%\Blender Foundation\Blender\<version>\scripts\addons"
   ```
   Replace `<version>` with your Blender version (e.g., `4.2`)
3. Create a symbolic link:
   ```cmd
   mklink /D blender_jps "C:\path\to\BlenderJPS\blender_jps"
   ```
   Replace `C:\path\to\BlenderJPS\blender_jps` with the actual path to your `blender_jps` folder

**macOS/Linux:**
1. Open Terminal
2. Navigate to your Blender addons directory:
   ```bash
   cd ~/Library/Application\ Support/Blender/<version>/scripts/addons  # macOS
   # or
   cd ~/.config/blender/<version>/scripts/addons  # Linux
   ```
3. Create a symbolic link:
   ```bash
   ln -s /path/to/BlenderJPS/blender_jps blender_jps
   ```

4. Open Blender
5. Go to **Edit → Preferences → Add-ons**
6. Search for "JuPedSim" and enable the addon

### Step 3: Install Dependencies (IMPORTANT)

The addon requires the `pedpy` Python package. To install it:

1. **Close Blender completely**
2. **Run Blender as Administrator** (Windows) or with elevated privileges (macOS/Linux)
   - Windows: Right-click Blender → "Run as administrator"
   - macOS: `sudo /Applications/Blender.app/Contents/MacOS/Blender`
   - Linux: `sudo blender`
3. Go to **Edit → Preferences → Add-ons**
4. Find "BlenderJPS - JuPedSim Importer" and expand its settings
5. Click **Install Dependencies**
6. Wait for the installation to complete
7. **Restart Blender** (normal mode, no admin needed)

## Usage

1. Open Blender and go to the **3D Viewport**
2. Open the sidebar (press `N` if hidden)
3. Find the **JuPedSim** tab
4. Click **Browse...** to select your SQLite trajectory file
5. (Optional) Adjust **Load Every Nth Frame** to downsample temporal resolution for faster loading
   - `1` = Load all frames (default)
   - `2` = Load every 2nd frame (50% of keyframes)
   - `10` = Load every 10th frame (10% of keyframes) etc.
6. Click **Load Simulation**

### What Gets Created

- **JuPedSim_Agents** collection: Contains animated empty objects (sphere display) for each agent
  - Agents automatically hide after reaching their destination
- **JuPedSim_Geometry** collection: Contains curve objects for boundaries and obstacles
- Animation timeline is automatically set to match the simulation frames

## Simulation Data Structure

The addon uses [PedPy](https://github.com/PedestrianDynamics/PedPy) to read JuPedSim SQLite files containing:

- **Trajectory data**: Agent positions over time (x, y coordinates per frame)
- **Walkable area**: The geometry defining where agents can move

## Troubleshooting

### "Dependencies not installed" error
- Make sure you ran Blender as Administrator when installing dependencies
- Check the Blender console (Window → Toggle System Console on Windows) for error messages
- Try reinstalling dependencies from the addon preferences

### "File not found" error
- Use absolute paths or ensure the file path is correct
- Check that the SQLite file is a valid JuPedSim trajectory file

### Agents appear at wrong scale
- JuPedSim uses meters as units. Make sure your Blender scene is set to metric units
- Agents are created as 1-meter diameter empty objects (sphere display) by default

### Loading takes too long
- Use the **Load Every Nth Frame** option to downsample the temporal resolution
- For very large simulations, try values like 5 or 10 to significantly reduce loading time
- Linear interpolation will fill in the gaps between keyframes for smooth animation

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## Acknowledgments

- [JuPedSim](https://github.com/PedestrianDynamics/jupedsim) - The pedestrian dynamics simulator
- [PedPy](https://github.com/PedestrianDynamics/PedPy) - Python library for pedestrian dynamics analysis

