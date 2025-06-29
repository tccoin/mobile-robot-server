import numpy as np
from scipy import interpolate
import matplotlib.pyplot as plt
def fit_smoothing_spline(points, smoothing_factor=0,n=1000):
    """
    Fits a smoothing spline to a sequence of 2D points and calculates its heading.
    Args:
        points (np.ndarray): An array of shape (N, 2) representing the 2D points.
        smoothing_factor (float): A non-negative smoothing factor.
                                  s=0 corresponds to an interpolating spline.
                                  A larger s means more smoothing. A good starting
                                  point is len(points).
    Returns:
        tuple: A tuple containing:
               - x_fine (np.ndarray): Evaluated x-coordinates of the spline.
               - y_fine (np.ndarray): Evaluated y-coordinates of the spline.
               - theta_fine (np.ndarray): Heading angle (in radians) at each point.
    """
    # Unpack the points into x and y
    if len(points)<4:
        points = np.vstack((points[:-1],points[-1:],points[-1:],points[-1:]))
    x = points[:, 0]
    y = points[:, 1]
    # --- 1. Parameterization ---
    # We use cumulative chordal distance as the parameter t.
    distance = np.cumsum(np.sqrt(np.sum(np.diff(points, axis=0)**2, axis=1)))
    t = np.insert(distance, 0, 0)
    # Ensure t is strictly increasing
    if not np.all(np.diff(t) > 0):
        for i in range(1, len(t)):
            if t[i] <= t[i-1]:
                t[i] = t[i-1] + 1e-6
    num_points = len(points)
    # if num_points<=3:

        #     # The 'curve' is just the original points connected by lines.
        #     # We return the points' coordinates directly.
        # print(f"Warning: {num_points} points provided. Cannot fit a cubic spline (k=3). "
        #         "Falling back to straight line segments.")
        # x = points[:, 0]
        # y = points[:, 1]
        
        # # Calculate headings for the N-1 segments between points
        # dx = np.diff(x)
        # dy = np.diff(y)
        # segment_headings = np.arctan2(dy, dx)
        
        # # Create an array of the correct size (N) to store the heading at each point
        # headings = np.zeros(num_points)
        
        # # The heading at each point is the direction of the segment leaving it
        # headings[:-1] = segment_headings
        
        # # For the last point, there's no leaving segment.
        # # A reasonable convention is to use the heading of the segment arriving at it.
        # headings[-1] = segment_headings[-1]
        # # Calculate heading for each segment start point
        # return points,headings,np.linalg.norm(points-points[:1],axis=1)
    # --- 2. Spline Fitting ---
    # Fit a cubic B-spline for x(t) and y(t) separately.
    tck_x = interpolate.splrep(t, x, s=smoothing_factor, k=3)
    tck_y = interpolate.splrep(t, y, s=smoothing_factor, k=3)
    # --- 3. Evaluation and Derivative Calculation ---
    # Evaluate the splines on a finer grid of the parameter t.
    t_fine = np.linspace(t.min(), t.max(), n)
    # Evaluate spline positions
    x_fine = interpolate.splev(t_fine, tck_x)
    y_fine = interpolate.splev(t_fine, tck_y)
    # Evaluate spline first derivatives (dx/dt, dy/dt)
    dx_dt = interpolate.splev(t_fine, tck_x, der=1)
    dy_dt = interpolate.splev(t_fine, tck_y, der=1)
    # --- 4. Calculate Heading ---
    # The heading is the angle of the tangent vector (dx/dt, dy/dt)
    theta_fine = np.arctan2(dy_dt, dx_dt)
    return np.vstack((x_fine,y_fine)).T,theta_fine,t_fine
def get_goal(wps,distance,x,y,lookahead):
    d = np.linalg.norm(wps-np.array([[x,y]]),axis=1)
    index = np.argmin(d)
    distance = np.absolute(distance[index:]-distance[index]-lookahead)
    lookahead_idx = np.argmin(distance)
    target_idx =  index+lookahead_idx
    return target_idx
class Planner:
    def __init__(self,lookahead=0.1,max_vx = 2,min_vx=-0.2,max_vy=0,max_vw=2,cruise_vel=0.8,Kp_x = 1,Kp_w = 2):
        self.wps = None
        self.lookahead = lookahead
        self.max_vx,self.max_vy,self.max_vw = max_vx,max_vy,max_vw
        self.min_vx = min_vx
        self.cruise_vel = cruise_vel

        self.xgoal,self.ygoal,self.thetagoal = None,None,None

        self.Kp_x = Kp_x
        self.Kp_w = Kp_w

    def update_waypoints(self,waypoints):
        self.wps,self.theta,self.distance = fit_smoothing_spline(waypoints,n=1600)
    def _dtheta_ds(self,x,y):
        idx = get_goal(self.wps,self.distance,x,y,self.lookahead)
        if(idx==len(self.wps)-1):
            return 0
        self.dtheta = self.theta[idx+1]-self.theta[idx]
        self.ds = self.distance[idx+1]-self.distance[idx]
        return self.dtheta/self.ds #use chain rule to get dtheta/dt
    def _step(self,x,y,theta,lookahead):
        idx = get_goal(self.wps,self.distance,x,y,lookahead)
        target_pos = self.wps[idx]
        dx = target_pos[0]-x
        dy = target_pos[1]-y
        ddx = np.cos(-theta)*dx-np.sin(-theta)*dy
        ddy = np.sin(-theta)*dx+np.cos(-theta)*dy
        dt = np.arctan2(ddy,ddx)
        target_heading = self.theta[idx]-theta

        if(target_heading>np.pi):
            target_heading-=np.pi*2
        if(target_heading<-np.pi):
            target_heading+=np.pi*2
        # w1 =(ddx*ddx+ddy*ddy)*2
        # w2 = 0
        # if idx>1590: #prioritize correction when not close to target
        #     w2 = 1
        #     w1 = 0
        # dt = (w2*target_heading+w1*dt)/(w1+w2)
        # return ddx*10,ddy*10,dt*10
        return ddx,ddy,dt
    
    # get the dispacement vector between the robot 
    def get_tracking_error(self):
        return self._step(self.xgoal,self.ygoal,0,0)
    
    def step(self,x,y,theta):
        self.xgoal,self.ygoal,self.thetagoal = x,y,theta # keep track of current target

        cmd_x,cmd_y,cmd_w = self._step(x,y,theta,self.lookahead)
        
        t_vec = np.array([cmd_x,cmd_y])
        t_norm = np.linalg.norm(t_vec)
        if t_norm<0.05:
            u_vec = np.array([0.,0.])
        else:
            u_vec = t_vec/t_norm
        
        # d_to_destination = np.linalg.norm(self.wps[-1]-np.array([x,y]))
        # vlimit = np.sqrt(2*0.6*d_to_destination)
        # cruise_vel = min(vlimit, self.cruise_vel)
        
        #feedforward and feedback
        e_vec = u_vec*max(t_norm-self.lookahead,0)
        cmd_x,cmd_y = u_vec*self.cruise_vel+e_vec*self.Kp_x
        
        # P-control only
        # if t_norm<0.1:
        #     cmd_x, cmd_y = 0, 0
        # else:
        #     cmd_x, cmd_y = t_vec*self.Kp_x

        # cmd_x/=(1+10*np.abs(cmd_w)) #slow down if the turning loop can't keep up

        cmd_w = cmd_w*self.Kp_w #Proportional control
        if len(self.wps)>3:
            cmd_w+=self._dtheta_ds(x,y)*cmd_x/(1+2*np.abs(cmd_w)) #feedforward control
        
        # stop if distance is close to target
        if t_norm<self.lookahead:
            cmd_w = 0.
        
        self.cmd_x,self.cmd_y,self.cmd_w = np.clip(cmd_x,self.min_vx,self.max_vx),np.clip(cmd_y,-self.max_vy,self.max_vy),np.clip(cmd_w,-self.max_vw,self.max_vw)
        return self.cmd_x, self.cmd_y, self.cmd_w
# --- Main part of the script ---
if __name__ == "__main__":
    # Define a sequence of 2D points.
    # These points have some noise and a sharp turn to demonstrate the smoothing.
    # points = np.array([
    #     [0, 0], [1, -2.5], [2, -3], [3, -2],
    #     [4, -2], [5, -1], [6, 1.2], [7, 2.2],
    #     [7.5, 4], [7, 6], [6, 7], [4.5, 7.2],
    #     [3, 6], [2, 4.5], [1.5, 3.5]
    # ])
    points = np.array([
        [0, 0], [0,1], [2,2]
    ])
    # --- Fit splines with different smoothing factors ---
    # Case 1: Interpolating spline (high curvature)
    # s=0 means the spline must pass through all points.
    wps,theta_interp,distance = fit_smoothing_spline(points, smoothing_factor=0)
    # --- Plot the results ---
    plt.style.use('seaborn-v0_8-whitegrid')
    fig, ax = plt.subplots(figsize=(10, 8))
    # Plot the original points
    ax.plot(points[:, 0], points[:, 1], 'ro', label='Original Points', markersize=8)
    # Plot the splines
    ax.plot(wps[:,0], wps[:,1], 'k-', lw=2, label='Interpolating Spline (s=0)')
    tx,ty = 1.4,0.87
    idx = get_goal(wps,distance,tx,ty,0.3)
    goal = wps[idx]
    ax.scatter(tx,ty)
    ax.scatter(goal[0],goal[1])
    # Configure the plot
    ax.set_title('Fitting Splines with Different Smoothing Factors', fontsize=16)
    ax.set_xlabel('X coordinate', fontsize=12)
    ax.set_ylabel('Y coordinate', fontsize=12)
    ax.legend(fontsize=12)
    ax.axis('equal')
    plt.show()