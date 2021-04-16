import numpy as np
import scipy.io as sio
import argparse
from camera import Camera
from plotting import *


# A very simple, but useful method to take the difference between the
# first and second element (usually for 2D vectors)
def diff(x):
    return x[1] - x[0]


'''
FORM_INITIAL_VOXELS  create a basic grid of voxels ready for carving

Arguments:
    xlim - The limits of the x dimension given as [xmin xmax]

    ylim - The limits of the y dimension given as [ymin ymax]

    zlim - The limits of the z dimension given as [zmin zmax]

    num_voxels - The approximate number of voxels we desire in our grid

Returns:
    voxels - An ndarray of size (N, 3) where N is approximately equal the 
        num_voxels of voxel locations.

    voxel_size - The distance between the locations of adjacent voxels
        (a voxel is a cube)

Our initial voxels will create a rectangular prism defined by the x,y,z
limits. Each voxel will be a cube, so you'll have to compute the
approximate side-length (voxel_size) of these cubes, as well as how many
cubes you need to place in each dimension to get around the desired
number of voxel. This can be accomplished by first finding the total volume of
the voxel grid and dividing by the number of desired voxels. This will give an
approximate volume for each cubic voxel, which can then be used to find the 
side-length. 
'''
def form_initial_voxels(xlim, ylim, zlim, num_voxels):
    # compute total volume of the voxel grid
    voxel_grid_vol = (xlim[1] - xlim[0]) * (ylim[1] - ylim[0]) * (zlim[1] - zlim[0])
    # find volume of each voxel
    voxel_vol = voxel_grid_vol / num_voxels
    # find side length of each voxel
    voxel_side_len = np.cbrt(voxel_vol)
    # build initial voxel grid
    initial_voxels = []
    for x in np.arange(xlim[0], xlim[1], voxel_side_len):
        for y in np.arange(ylim[0], ylim[1], voxel_side_len):
            for z in np.arange(zlim[0], zlim[1], voxel_side_len):
                initial_voxels.append([x, y, z])
    initial_voxels = np.array(initial_voxels, dtype=np.float64)
    return initial_voxels, voxel_side_len

'''
GET_VOXEL_BOUNDS: Gives a nice bounding box in which the object will be carved
from. We feed these x/y/z limits into the construction of the inital voxel
cuboid. 

Arguments:
    cameras - The given data, which stores all the information
        associated with each camera (P, image, silhouettes, etc.)

    estimate_better_bounds - a flag that simply tells us whether to set tighter
        bounds. We can carve based on the silhouette we use.

    num_voxels - If estimating a better bound, the number of voxels needed for
        a quick carving.

Returns:
    xlim - The limits of the x dimension given as [xmin xmax]

    ylim - The limits of the y dimension given as [ymin ymax]

    zlim - The limits of the z dimension given as [zmin zmax]

This method first finds a coarse bound and then estimates a tigther bound
by doing a quick carving of the object on a grid with very few voxels. From this coarse carving,
we can determine tighter bounds. Of course, these bounds may be too strict, so we should have 
a buffer of one voxel_size around the carved object. 
'''
def get_voxel_bounds(cameras, estimate_better_bounds = False, num_voxels = 4000):
    camera_positions = np.vstack([c.T for c in cameras])
    xlim = [camera_positions[:,0].min(), camera_positions[:,0].max()]
    ylim = [camera_positions[:,1].min(), camera_positions[:,1].max()]
    zlim = [camera_positions[:,2].min(), camera_positions[:,2].max()]

    # For the zlim we need to see where each camera is looking. 
    camera_range = 0.6 * np.sqrt(diff( xlim )**2 + diff( ylim )**2)
    for c in cameras:
        viewpoint = c.T - camera_range * c.get_camera_direction()
        zlim[0] = min( zlim[0], viewpoint[2] )
        zlim[1] = max( zlim[1], viewpoint[2] )

    # Move the limits in a bit since the object must be inside the circle
    xlim = xlim + diff(xlim) / 4 * np.array([1, -1])
    ylim = ylim + diff(ylim) / 4 * np.array([1, -1])

    if estimate_better_bounds:
        voxels, voxel_size = form_initial_voxels(xlim, ylim, zlim, num_voxels)
        for c in cameras:
            voxels = carve(voxels, c)

        xlim = [voxels[:,0].min()-voxel_size, voxels[:,0].max()+voxel_size]
        ylim = [voxels[:,1].min()-voxel_size, voxels[:,1].max()+voxel_size]
        zlim = [voxels[:,2].min()-voxel_size, voxels[:,2].max()+voxel_size]

    xlim = np.array(xlim, dtype=np.float64)
    ylim = np.array(ylim, dtype=np.float64)
    zlim = np.array(zlim, dtype=np.float64)
    return xlim, ylim, zlim
    
'''
CARVE: carves away voxels that are not inside the silhouette contained in 
    the view of the camera. The resulting voxel array is returned.

Arguments:
    voxels - an Nx3 matrix where each row is the location of a cubic voxel

    camera - The camera we are using to carve the voxels with. Useful data
        stored in here are the "silhouette" matrix, "image", and the
        projection matrix "P". 

Returns:
    voxels - a subset of the argument passed that are inside the silhouette
'''
def carve(voxels, camera):
    ## start carving for z distance lower to higher
    # get 2d position of each voxel and find out whether
    # or not it is contained within the silhouette
    carved_voxels = []
    # compute the projection matrix
    Tmat = np.eye(4, dtype=np.float64)
    Tmat[:3,3] = camera.T
    Rmat = np.eye(4, dtype=np.float64)
    Rmat[:3,:3] = camera.R
    P = np.dot(camera.K, np.dot(Rmat, Tmat)[:3])
    # go through each voxel
    for voxel in voxels:
        # compute 2d projection of this voxel
        voxel_projection_2d = np.dot(camera.P, np.append(voxel, 1.0))
        voxel_projection_2d = np.array((voxel_projection_2d / voxel_projection_2d[-1])[:2], dtype=np.int32)
        # check if this point is within the silhouette
        if (voxel_projection_2d[0] >= 0) and (voxel_projection_2d[0] < camera.silhouette.shape[1]) and \
           (voxel_projection_2d[1] >= 0) and (voxel_projection_2d[1] < camera.silhouette.shape[0]) and \
           (camera.silhouette[voxel_projection_2d[1],voxel_projection_2d[0]] > 0): 
            carved_voxels.append(voxel)
    carved_voxels = np.array(carved_voxels, dtype=np.float64)
    return carved_voxels
    
'''
ESTIMATE_SILHOUETTE: Uses a very naive and color-specific heuristic to generate
the silhouette of an object

Arguments:
    im - The image containing a known object. An ndarray of size (H, W, C).

Returns:
    silhouette - An ndarray of size (H, W), where each pixel location is 0 or 1.
        If the (i,j) value is 0, then that pixel location in the original image 
        does not correspond to the object. If the (i,j) value is 1, then that
        that pixel location in the original image does correspond to the object.
'''
def estimate_silhouette(im):
    return np.logical_and(im[:,:,0] > im[:,:,2], im[:,:,0] > im[:,:,1] )


if __name__ == '__main__':
    estimate_better_bounds = True
    use_true_silhouette = True
    frames = sio.loadmat('frames.mat')['frames'][0]
    cameras = [Camera(x) for x in frames]

    # Generate the silhouettes based on a color heuristic
    if not use_true_silhouette:
        for i, c in enumerate(cameras):
            c.true_silhouette = c.silhouette
            c.silhouette = estimate_silhouette(c.image)
            if i == 0:
                plt.figure()
                plt.subplot(121)
                plt.imshow(c.true_silhouette, cmap = 'gray')
                plt.title('True Silhouette')
                plt.subplot(122)
                plt.imshow(c.silhouette, cmap = 'gray')
                plt.title('Estimated Silhouette')
                plt.show()

    # Generate the voxel grid
    # You can reduce the number of voxels for faster debugging, but
    # make sure you use the full amount for your final solution
    num_voxels = 6e6
    xlim, ylim, zlim = get_voxel_bounds(cameras, estimate_better_bounds)

    # This part is simply to test forming the initial voxel grid
    voxels, voxel_size = form_initial_voxels(xlim, ylim, zlim, 4000)
    plot_surface(voxels)
    voxels, voxel_size = form_initial_voxels(xlim, ylim, zlim, num_voxels)

    # Test the initial carving
    voxels = carve(voxels, cameras[0])
    if use_true_silhouette:
        plot_surface(voxels)

    # Result after all carvings
    for c in cameras:
        voxels = carve(voxels, c)  
    plot_surface(voxels, voxel_size)
