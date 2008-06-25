 
class Culvert_flow:
    """Culvert flow - transfer water from one hole to another
    
    Using Momentum as Calculated by Culvert Flow !!
    Could be Several Methods Investigated to do This !!!

    2008_May_08
    To Ole:
    OK so here we need to get the Polygon Creating code to create polygons for the culvert Based on
    the two input Points (X0,Y0) and (X1,Y1) - need to be passed to create polygon

    The two centers are now passed on to create_polygon.
    

    Input: Two points, pipe_size (either diameter or width, height), mannings_rougness,
    inlet/outlet energy_loss_coefficients, internal_bend_coefficent,
    top-down_blockage_factor and bottom_up_blockage_factor
    
    
    And the Delta H enquiry should be change from Openings in line 412 to the enquiry Polygons infront
    of the culvert
    At the moment this script uses only Depth, later we can change it to Energy...

    Once we have Delta H can calculate a Flow Rate and from Flow Rate an Outlet Velocity
    The Outlet Velocity x Outlet Depth = Momentum to be applied at the Outlet...
	
    """	

    def __init__(self,
                 domain,
                 label=None, 
                 description=None,
                 end_point0=None, 
                 end_point1=None,
                 width=None,
                 height=None,
                 diameter=None,
                 manning=None,          # Mannings Roughness for Culvert
                 invert_level0=None,    # Invert level if not the same as the Elevation on the Domain
                 invert_level1=None,    # Invert level if not the same as the Elevation on the Domain
                 loss_exit=None,
                 loss_entry=None,
                 loss_bend=None,
                 loss_special=None,
                 blockage_topdwn=None,
                 blockage_bottup=None,
                 culvert_routine=None,
                 verbose=False):
        
        from Numeric import sqrt, sum

        # Input check
        if diameter is not None:
            self.culvert_type = 'circle'
            self.diameter = diameter
            if height is not None or width is not None:
                msg = 'Either diameter or width&height must be specified, but not both.'
                raise Exception, msg
        else:
            if height is not None:
                if width is None:
                    self.culvert_type = 'square'                                
                    width = height
                else:
                    self.culvert_type = 'rectangle'
            elif width is not None:
                if height is None:
                    self.culvert_type = 'square'                                
                    height = width
            else:
                msg = 'Either diameter or width&height must be specified.'
                raise Exception, msg                
                
            if height == width:
                self.culvert_type = 'square'                                                
                
            self.height = height
            self.width = width

            
        assert self.culvert_type in ['circle', 'square', 'rectangle']
        
        # Set defaults
        if manning is None: manning = 0.012   # Set a Default Mannings Roughness for Pipe
        if loss_exit is None: loss_exit = 1.00
        if loss_entry is None: loss_entry = 0.50
        if loss_bend is None: loss_bend=0.00
        if loss_special is None: loss_special=0.00
        if blockage_topdwn is None: blockage_topdwn=0.00
        if blockage_bottup is None: blockage_bottup=0.00
        if culvert_routine is None: culvert_routine=boyd_generalised_culvert_model
        if label is None: label = 'culvert_flow_' + id(self) 
        
        # Open log file for storing some specific results...
        self.log_filename = label + '.log' 
        self.label = label


        # Create the fundamental culvert polygons from POLYGON 
        P = create_culvert_polygons(end_point0,
                                    end_point1,
                                    width=width,   
                                    height=height)
        
        if verbose is True:
            pass
            #plot_polygons([[end_point0, end_point1],
            #               P['exchange_polygon0'],
            #               P['exchange_polygon1'],
            #               P['enquiry_polygon0'],
            #               P['enquiry_polygon1']],
            #              figname='culvert_polygon_output')
        
        self.openings = []
        self.openings.append(Inflow(domain,
                                    polygon=P['exchange_polygon0']))

        self.openings.append(Inflow(domain,
                                    polygon=P['exchange_polygon1']))                                    


        # Assume two openings for now: Referred to as 0 and 1
        assert len(self.openings) == 2
        
        # Store basic geometry 
        self.end_points = [end_point0, end_point1]
        self.invert_levels = [invert_level0, invert_level1]                
        self.enquiry_polygons = [P['enquiry_polygon0'], P['enquiry_polygon1']]
        self.vector = P['vector']
        self.length = P['length']; assert self.length > 0.0
        self.verbose = verbose
        self.last_time = 0.0        
        self.temp_keep_delta_t = 0.0
        

        # Store hydraulic parameters 
        self.manning = manning
        self.loss_exit = loss_exit
        self.loss_entry = loss_entry
        self.loss_bend = loss_bend
        self.loss_special = loss_special
        self.sum_loss = loss_exit + loss_entry + loss_bend + loss_special
        self.blockage_topdwn = blockage_topdwn
        self.blockage_bottup = blockage_bottup

        # Store culvert routine
        self.culvert_routine = culvert_routine

        
        # Create objects to update momentum (a bit crude at this stage)

        
        xmom0 = General_forcing(domain, 'xmomentum',
                                polygon=P['exchange_polygon0'])

        xmom1 = General_forcing(domain, 'xmomentum',
                                polygon=P['exchange_polygon1'])

        ymom0 = General_forcing(domain, 'ymomentum',
                                polygon=P['exchange_polygon0'])

        ymom1 = General_forcing(domain, 'ymomentum',
                                polygon=P['exchange_polygon1'])

        self.opening_momentum = [ [xmom0, ymom0], [xmom1, ymom1] ]
        

        # Print something
        s = 'Culvert Effective Length = %.2f m' %(self.length)
        log_to_file(self.log_filename, s)
   
        s = 'Culvert Direction is %s\n' %str(self.vector)
        log_to_file(self.log_filename, s)        
        
    def __call__(self, domain):
        from anuga.utilities.numerical_tools import mean
        from anuga.utilities.polygon import inside_polygon
        from anuga.config import g, epsilon
        from Numeric import take, sqrt
        from anuga.config import velocity_protection        


        log_filename = self.log_filename
         
        # Time stuff
        time = domain.get_time()
        delta_t = time-self.last_time
        s = '\nTime = %.2f, delta_t = %f' %(time, delta_t)
        log_to_file(log_filename, s)
        
        msg = 'Time did not advance'
        if time > 0.0: assert delta_t > 0.0, msg


        # Get average water depths at each opening        
        openings = self.openings   # There are two Opening [0] and [1]
        for i, opening in enumerate(openings):
            stage = domain.quantities['stage'].get_values(location='centroids',
                                                          indices=opening.exchange_indices)
            elevation = domain.quantities['elevation'].get_values(location='centroids',
                                                                  indices=opening.exchange_indices)

            # Indices corresponding to energy enquiry field for this opening
            coordinates = domain.get_centroid_coordinates() # Get all centroid points (x,y)
            enquiry_indices = inside_polygon(coordinates, self.enquiry_polygons[i]) 
            
            
            # Get model values for points in enquiry polygon for this opening
            dq = domain.quantities
            stage = dq['stage'].get_values(location='centroids', indices=enquiry_indices)
            xmomentum = dq['xmomentum'].get_values(location='centroids', indices=enquiry_indices)
            ymomentum = dq['ymomentum'].get_values(location='centroids', indices=enquiry_indices)                        
            elevation = dq['elevation'].get_values(location='centroids', indices=enquiry_indices)
            depth = stage - elevation

            # Compute mean values of selected quantitites in the enquiry area in front of the culvert
            # Epsilon handles a dry cell case
            ux = xmomentum/(depth+velocity_protection/depth)   # Velocity (x-direction)
            uy = ymomentum/(depth+velocity_protection/depth)   # Velocity (y-direction)
            v = mean(sqrt(ux**2+uy**2))      # Average velocity
            w = mean(stage)                  # Average stage

            # Store values at enquiry field
            opening.velocity = v


            # Compute mean values of selected quantitites in the exchange area in front of the culvert
            # Stage and velocity comes from enquiry area and elevation from exchange area
            
            # Use invert level instead of elevation if specified
            invert_level = self.invert_levels[i]
            if invert_level is not None:
                z = invert_level
            else:
                elevation = dq['elevation'].get_values(location='centroids', indices=opening.exchange_indices)
                z = mean(elevation)                   # Average elevation
                
            # Estimated depth above the culvert inlet
            d = w - z

            if d < 0.0:
                # This is possible since w and z are taken at different locations
                #msg = 'D < 0.0: %f' %d
                #raise msg
                d = 0.0
            
            # Ratio of depth to culvert height.
            # If ratio > 1 then culvert is running full
            ratio = d/self.height  
            opening.ratio = ratio
                
            # Average measures of energy in front of this opening
            Es = d + 0.5*v**2/g  #  Specific energy in exchange area
            Et = w + 0.5*v**2/g  #  Total energy in the enquiry area
            opening.total_energy = Et
            opening.specific_energy = Es            
            
            # Store current average stage and depth with each opening object 
            opening.depth = d
            opening.stage = w
            opening.elevation = z
            

        #################  End of the FOR loop ################################################

            
        # We now need to deal with each opening individually

        # Determine flow direction based on total energy difference
        delta_Et = openings[0].total_energy - openings[1].total_energy

        if delta_Et > 0:
            #print 'Flow U/S ---> D/S'
            inlet=openings[0]
            outlet=openings[1]

            inlet.momentum = self.opening_momentum[0]
            outlet.momentum = self.opening_momentum[1]

        else:
            #print 'Flow D/S ---> U/S'
            inlet=openings[1]
            outlet=openings[0]

            inlet.momentum = self.opening_momentum[1]
            outlet.momentum = self.opening_momentum[0]
            
            delta_Et = -delta_Et

        msg = 'Total energy difference is negative'
        assert delta_Et > 0.0, msg

        delta_h = inlet.stage - outlet.stage
        delta_z = inlet.elevation - outlet.elevation
        culvert_slope = (delta_z/self.length)

        if culvert_slope < 0.0:
            # Adverse gradient - flow is running uphill
            # Flow will be purely controlled by uphill outlet face
            print 'WARNING: Flow is running uphill. Watch Out!', inlet.elevation, outlet.elevation


        s = 'Delta total energy = %.3f' %(delta_Et)
        log_to_file(log_filename, s)

        
        Q, barrel_velocity, culvert_outlet_depth = self.culvert_routine(self, inlet, outlet, delta_Et, g)
        #####################################################
        barrel_momentum = barrel_velocity*culvert_outlet_depth
                
        s = 'Barrel velocity = %f' %barrel_velocity
        log_to_file(log_filename, s)

        # Compute momentum vector at outlet
        outlet_mom_x, outlet_mom_y = self.vector * barrel_momentum
            
        s = 'Directional momentum = (%f, %f)' %(outlet_mom_x, outlet_mom_y)
        log_to_file(log_filename, s)

        delta_t = time - self.last_time
        if delta_t > 0.0:
            xmomentum_rate = outlet_mom_x - outlet.momentum[0].value
            xmomentum_rate /= delta_t
                
            ymomentum_rate = outlet_mom_y - outlet.momentum[1].value
            ymomentum_rate /= delta_t
                    
            s = 'X Y MOM_RATE = (%f, %f) ' %(xmomentum_rate, ymomentum_rate)
            log_to_file(log_filename, s)                    
        else:
            xmomentum_rate = ymomentum_rate = 0.0


        # Set momentum rates for outlet jet
        outlet.momentum[0].rate = xmomentum_rate
        outlet.momentum[1].rate = ymomentum_rate

        # Remember this value for next step (IMPORTANT)
        outlet.momentum[0].value = outlet_mom_x
        outlet.momentum[1].value = outlet_mom_y                    

        if int(domain.time*100) % 100 == 0:
            s = 'T=%.5f, Culvert Discharge = %.3f f'\
                %(time, Q)
            s += ' Depth= %0.3f  Momentum = (%0.3f, %0.3f)'\
                 %(culvert_outlet_depth, outlet_mom_x,outlet_mom_y)
            s += ' Momentum rate: (%.4f, %.4f)'\
                 %(xmomentum_rate, ymomentum_rate)                    
            s+='Outlet Vel= %.3f'\
                %(barrel_velocity)
            log_to_file(log_filename, s)
            
                


       
        # Execute flow term for each opening
        # This is where Inflow objects are evaluated and update the domain
        for opening in self.openings:
            opening(domain)

        # Execute momentum terms
        # This is where Inflow objects are evaluated and update the domain
        outlet.momentum[0](domain)
        outlet.momentum[1](domain)        
            
        # Store value of time    
        self.last_time = time


